# Third-party decoder

FFmpeg is a separate executable, invoked as a child process. Its binary is not
tracked in this repository. The original deployment used the ARMHF static
FFmpeg 7.0.2 build distributed by John Van Sickle:

- Download: https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-armhf-static.tar.xz
- Build information and source links: https://johnvansickle.com/ffmpeg/
- FFmpeg project: https://ffmpeg.org/
- Verified executable SHA-256: `0afba4a11110e6e402053e0fc14c33a7eb207d7a588688ae87dba471a0f06c71`

The selected build is GPLv3; its license text is included as `GPLv3.txt`.
Redistributing that executable carries its own license obligations, including
applicable corresponding-source requirements. The license text alone is not a
substitute for the required source when distributing a binary. This repository
supplies the client source and download instructions, rather than a binary bundle.

Python dependencies `aiohttp` and Pillow are supplied by the tested firmware and
are not vendored here. They retain their respective upstream licenses.
The original application code and documentation are licensed under 0BSD in
`LICENSE`. That grant does not extend to FFmpeg, its license text, or the Python
dependencies. The GPLv3 notice does not relicense the original application source.
