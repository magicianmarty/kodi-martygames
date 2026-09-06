# How everyone else opens a hardware framebuffer

Research done 2026-09-06 after five rounds of fixing Kodi's hardware rendering
path by inference. Sources: `libretro.h` (upstream master), RetroArch
`gfx/drivers/gl2.c` and `runloop.c`, and the Kodi 22 game API headers.

The short version: **our design allocates lazily and RetroArch's does not**, and
almost every problem we hit came from that difference.

## The contract

From `libretro.h`, on `retro_hw_render_callback`:

> Called when a context has been created or when it has been reset.
> **An OpenGL context is only valid after `context_reset()` has been called.**

and, on the framebuffer callback itself:

> Set by frontend. **TODO: This is rather obsolete. The frontend should not be
> providing preallocated framebuffers.**

So the frontend owns the ordering, the core owns nothing until `context_reset`,
and the whole `get_current_framebuffer` mechanism is legacy that GL cores still
lean on.

## What RetroArch actually does

**`SET_HW_RENDER` creates nothing.** `runloop.c` validates the requested context
type, installs two function pointers, copies the struct into video state, and
returns:

```c
cb->get_current_framebuffer = video_driver_get_current_framebuffer;
cb->get_proc_address        = video_driver_get_proc_address;
memcpy(hwr, cb, sizeof(*cb));
```

No context creation, no stream opening, no allocation. It is pure registration.

**The FBOs are built during video driver init**, from `gl2_init()`:

```c
if ((gl->flags & GL2_FLAG_HW_RENDER_USE)
      && !gl2_renderchain_init_hw_render(gl, chain, gl->tex_w, gl->tex_h))
   goto error;
```

`tex_w`/`tex_h` come from `retro_get_system_av_info()`'s **maximum** geometry,
known once `retro_load_game()` has returned. Everything is allocated before the
core runs a single frame.

**One buffer, not a pool** (`gl2.c`):

```c
if (gl->flags & GL2_FLAG_HW_RENDER_USE)
{
   /* All on GPU, no need to excessively create textures. */
   gl->textures = 1;
}
```

**So the hot path cannot fail:**

```c
static uintptr_t gl2_get_current_framebuffer(void *data)
{
   gl2_t *gl = (gl2_t*)data;
   if (!gl || (!(gl->flags & GL2_FLAG_HAVE_FBO)))
      return 0;
   return gl->hw_render_fbo[(gl->tex_index + 1) % gl->textures];
}
```

A lookup. No allocation, no locking, no pool, no "is a renderer visible yet".

**Depth and stencil** match what we already wrote, which is reassuring:
`GL_DEPTH24_STENCIL8` when the core asked for stencil, `GL_DEPTH_COMPONENT16`
otherwise; and on GLES the same renderbuffer is attached to `GL_DEPTH_ATTACHMENT`
and `GL_STENCIL_ATTACHMENT` separately, because - their words - *"GLES2 is a bit
weird, as always. There's no GL_DEPTH_STENCIL_ATTACHMENT like in desktop GL."*

**Shared contexts** are handled with an explicit bracket around GL work:

```c
if (gl->flags & GL2_FLAG_SHARED_CONTEXT_USE)
   gl->ctx_driver->bind_hw_render(gl->ctx_data, true);
... create FBOs ...
if (gl->flags & GL2_FLAG_SHARED_CONTEXT_USE)
   gl->ctx_driver->bind_hw_render(gl->ctx_data, false);
```

We have no equivalent. Our pool makes its context current once and leaves it,
which has worked so far but is worth remembering if Kodi's own rendering starts
misbehaving during a game.

## Where Kodi differs, and what it costs

| | RetroArch | Kodi 22 |
|---|---|---|
| On `SET_HW_RENDER` | record only | opens a stream, creates a context, configures a render manager |
| FBO creation | up front, at driver init | lazily, on first `GetBuffer()` |
| Buffer count | exactly 1 | a pool with allocation-on-miss |
| `get_current_framebuffer` | pure lookup | walks pools, may allocate, may return 0 |
| Dimensions | `av_info` max geometry | **not available at all** (see below) |

Every defect this cost us was an ordering problem, and each one hid the next:

1. FBO renderer registered in the GBM window system, which this box never uses
2. `CRPProcessInfoAmlogic` inherited a `GetHwProcedureAddress()` returning null
3. EGL context created lazily, so the core read `glGetString(GL_EXTENSIONS)`
   before one existed and segfaulted inside its own `strstr()`
4. The context lookup cast to `CWinSystemEGL`, which the Amlogic window system
   declares the same accessors as but does not inherit
5. `Create()` chose its pools with `IsCompatible()`, which the software pool
   answers yes to, so it won the renderer and rejected `AV_PIX_FMT_NONE`

None of these exist in a design that allocates one framebuffer up front.

## The dimensions gap

`game_stream_video_properties` carries `nominal_width/height` and
`max_width/height` - but that is the **software** stream. The wrapper opens a
hardware stream with nothing at all:

```cpp
game_stream_properties streamProperties{GAME_STREAM_HW_FRAMEBUFFER};
```

There is no hardware equivalent of that struct, so **Kodi cannot know how big a
hardware framebuffer should be.** That is why `CRetroPlayerRendering::OpenStream()`
hardcodes 640x480, and why the wrapper asks for buffers with `GetBuffer(0, 0)`.

It matters for N64: GLideN64 renders at its own internal resolution, which is
often an upscale of 320x240, and RetroArch sizes its FBO from `av_info`'s
maximum rather than the nominal. A fixed 640x480 will be wrong for any core that
wants more.

Options, worst to best:

1. Keep a fixed size and accept clipping or scaling. Cheap, wrong for upscalers.
2. Take the maximum from `CRPProcessInfo`, if the game client populates it from
   `av_info` before the hardware stream opens. Needs checking.
3. Extend the game API with a `game_stream_hw_framebuffer_properties` carrying
   geometry, and teach the wrapper to fill it from `SET_SYSTEM_AV_INFO`. Correct,
   and an upstream contribution to both Kodi and kodi-game - but it means
   building our own `game.libretro`, which we currently take prebuilt from the
   CoreELEC repo.

## What to change next

In order, and all of it before touching the box again:

1. **Allocate one framebuffer in `Create()`**, at known dimensions, and hold it
   for the life of the stream. Not a pool, not on demand.
2. **Make `GetCurrentFramebuffer()` a lookup** that returns that framebuffer.
   It should be incapable of returning 0 once `Create()` has succeeded.
3. **Only then call `context_reset`.** Kodi currently fires
   `m_callback.HardwareContextReset()` from `CGameClientStreamHwFramebuffer::
   OpenStream()`, which is the right place *provided* step 1 has already run.
4. Decide the dimensions question above; option 2 first, since it needs no new
   API.

That reduces the remaining work to one behaviour - "hand back the same FBO every
time" - instead of the five-way ordering puzzle we have been unpicking.


## Root cause of the black screen, found 2026-09-06

Everything on Kodi's side now reports correct - `Hardware framebuffer 1 ready at
640x480`, `Creating renderer for FBO`, no GL errors, the core emulating at 88%
CPU - and the screen stays black. The reason is in **glsm**, the GL state
manager `mupen64plus-nx` renders through (`libretro-common/glsm/glsm.c`):

```c
default_framebuffer                  = glsm_get_current_framebuffer();

gl_state.framebuf[0].location        = default_framebuffer;
gl_state.framebuf[1].location        = default_framebuffer;
gl_state.framebuf[0].desired_location = default_framebuffer;
gl_state.framebuf[1].desired_location = default_framebuffer;

glBindFramebuffer(GL_FRAMEBUFFER, default_framebuffer);
```

**It asks once and caches the answer for the whole session.** The core runs that
setup from inside its `context_reset`:

```c
glsm_ctl(GLSM_CTL_STATE_CONTEXT_RESET, NULL);
if (!context_setup_first_init)
{
   glsm_ctl(GLSM_CTL_STATE_SETUP, NULL);   /* the query happens in here */
   context_setup_first_init = true;
}
```

And Kodi fires `context_reset` from *inside* the stream opening:

```cpp
if (stream->OpenStream(*hwProperties))
{
  m_stream = stream;
  m_callback.HardwareContextReset();   // CGameClientStreamHwFramebuffer::OpenStream
}
```

which runs before the wrapper's own `m_stream.Open()` has returned. So the
wrapper still thinks the stream is shut:

```cpp
uintptr_t CVideoStream::GetHwFramebuffer()
{
  if (!m_stream.IsOpen() || m_streamType != GAME_STREAM_HW_FRAMEBUFFER)
    return 0;      // <- here, every time, during context_reset
  ...
}
```

glsm caches **0**, binds framebuffer 0 for the session, and the core renders to
the default framebuffer - which on the pool's surfaceless context is nowhere at
all. No error is produced anywhere, which is why this survived five rounds of
fixing things that were also genuinely wrong.

### Why this cannot be fixed from Kodi alone

Deferring `HardwareContextReset()` does not work: nothing else would trigger it.
The client only touches GL through glsm, glsm only initialises during
`context_reset`, and it only queries the framebuffer during that initialisation.
Fire the reset later and the client never sets up at all.

The fix belongs in the wrapper, and it is small - `GetHwFramebuffer()` should
open the stream on demand exactly as `GetSwFramebuffer()` already does:

```cpp
bool CVideoStream::GetSwFramebuffer(...)
{
  if (!m_stream.IsOpen())
  {
    game_stream_properties properties{};
    ...
    m_stream.Open(properties);     // opens on demand
  }
```

The hardware path checks `IsOpen()` and gives up instead. Fixing it means
building `game.libretro` ourselves rather than taking the CoreELEC repo build -
the package already exists at
`packages/mediacenter/kodi-binary-addons/game.libretro`, so it is a patch and a
package bump, not new infrastructure.

**Worth an upstream PR to kodi-game.** It is a two-line change and it is the
difference between hardware rendering working and silently rendering nowhere.
