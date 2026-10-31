# GLKVM Mac Login

A small, one-shot command that runs **on a GLKVM**: capture its HDMI input, ask
DeepSeek to identify an empty macOS login password field, then enter the password
provided for that invocation. It exits after one attempt. There is no background
agent, conversation history, automatic login loop, or locally hosted model.

## License

The original code and documentation in this repository are available under
[Zero-Clause BSD (0BSD)](LICENSE), an [OSI-approved license](https://opensource.org/license/0bsd).
You may use, modify, sell, and redistribute them, including in closed-source
products, without requesting permission or retaining attribution/license notices.
The license provides the software without warranty.

This grant covers the original project material only. It does not relicense
FFmpeg, Python dependencies, or their license texts. The separately downloaded
FFmpeg build retains its GPLv3 terms; see [THIRD_PARTY.md](THIRD_PARTY.md).
The GPLv3 text here is a third-party notice, not this project's source license.

## Supported setup

Tested with a Buildroot-based ARMv7 GLKVM firmware reporting
`rmq1-1.8.3-release1-1-g8e7e8b2f4e`, Python 3.12, and the firmware's existing
`aiohttp` and Pillow packages. It uses these local GLKVM interfaces:

- `/run/kvmd/kvmd.sock`: authenticated control and HDMI status.
- `/run/kvmd/media.sock`: H.264 video over a local WebSocket.
- A separate ARMHF FFmpeg executable for decoding one H.264 keyframe.

This is firmware-specific software, not a generic client for every PiKVM or
GLKVM release. The capture path preserves the existing encoder settings. It does
not install a service or change the device's video, network, or boot configuration.

The target must show a **normal macOS system login screen**, with one selected
user and an empty password field. User selection, FileVault preboot unlock,
recovery, startup options, application password dialogs, waking a black screen,
and clearing existing password text are outside its scope.

## Install

Use `/userdata/glkvm-login-agent`; the supplied `mac-login` wrapper expects this
location. On the tested device, `/opt` is a separate small filesystem and is not
suitable for the decoder.

### 1. Prepare the decoder on your computer

The repository does **not** contain the FFmpeg binary. Download the ARMHF static
7.0.2 build separately from John Van Sickle:

```sh
mkdir -p decoder-download
cd decoder-download
curl -fL https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-armhf-static.tar.xz -o ffmpeg.tar.xz
tar -xJf ffmpeg.tar.xz
```

Locate the extracted `ffmpeg` executable and verify its SHA-256 before using it:

```text
0afba4a11110e6e402053e0fc14c33a7eb207d7a588688ae87dba471a0f06c71
```

On macOS, use `shasum -a 256 PATH_TO_EXTRACTED_FFMPEG`. If the upstream URL now
serves a different release or the checksum differs, stop and select a verified
compatible build; do not assume a moving download URL still contains this build.
Copy the verified executable into the repository directory as `ffmpeg`. It is
ignored by Git. See [THIRD_PARTY.md](THIRD_PARTY.md) for provenance and licensing.

### 2. Copy files to the GLKVM

Run from the repository directory on your computer. Replace `GLKVM_HOST` with the
hostname or address of your device. Authenticate using your own SSH credentials.

```sh
ssh root@GLKVM_HOST 'mkdir -p /userdata/glkvm-login-agent'
scp agent.py configure.py config.example.json mac-login test_agent.py README.md LICENSE THIRD_PARTY.md GPLv3.txt SHA256SUMS requirements.txt ffmpeg root@GLKVM_HOST:/userdata/glkvm-login-agent/
```

If the device lacks an SFTP subsystem, use `scp -O` instead of `scp`.
Then SSH into the device and run:

```sh
cd /userdata/glkvm-login-agent
sha256sum -c SHA256SUMS
chmod 755 ffmpeg mac-login
cp mac-login /usr/bin/mac-login
chmod 755 /usr/bin/mac-login
python3 -c 'import aiohttp; from PIL import Image'
mac-login configure
```

The firmware already supplied the Python dependencies in the tested setup.
`requirements.txt` lists them for other environments; installing packages or
changing the firmware's Python environment is not part of this installer.
The wrapper in `/usr/bin` may need reinstalling after a firmware update.

### 3. Configure credentials privately

`mac-login configure` prompts without echo for the GLKVM **web admin password**
and a DeepSeek API key. It creates `config.json`, `kvm-password`, and `deepseek-key`
next to the scripts with private permissions. It never asks you to save a Mac
password. When a KVM password file already exists, setup reuses it and asks only
for the API key; update that private file separately if your KVM password changes.

`config.example.json` contains paths and a generic web username only. The default
web username is `admin`; edit your private `config.json` if your device differs.
The DeepSeek endpoint and model are defined in `agent.py`:
`https://api.deepseek.com/chat/completions`, `deepseek-flash`.

## Log in once

SSH into the GLKVM while the Mac shows the supported login screen:

```sh
mac-login
```

Enter the Mac password at the hidden prompt. The password is used only by that
process, is not saved by the program, and is sent only to the GLKVM's local HID
interface. It is never included in a model request. An interactive SSH terminal
is required for the prompt; use `ssh -t` if necessary.

The positional form is also supported:

```sh
mac-login 'YOUR_MAC_PASSWORD'
```

Unlike the hidden prompt, this form can expose the password in shell history and
process arguments. Quote shell metacharacters correctly. Passwords must contain
printable ASCII characters and use the US keyboard layout; non-ASCII input and
other keyboard layouts are not supported. Password length is limited to 4096.

Each invocation makes at most **one model request and one password submission**.
There is no automatic retry after rejection or submission. A new invocation is a
new attempt; repeated incorrect passwords can affect macOS login attempt limits.

## Inspect without typing

```sh
mac-login --dry-run
mac-login --capture /tmp/login-check.jpg
```

- `--dry-run` captures and classifies once; it never sends keyboard or mouse input
  and does not need a Mac password. It does require an API key.
- `--capture` saves a JPEG locally without contacting DeepSeek or sending input.
  It does not need an API key. Remove the diagnostic image when finished.

Screenshots are not saved during normal execution. A dry run does not verify
that the returned point is correct or that a password would successfully log in.

## Recognition and input rules

The model must identify a normal system login, an empty password field, and a
confidence of at least **0.85**. This is the model's own score, not a calibrated
probability of success. It returns `field_1000` as two integer coordinates from
0 to 1000 relative to the full image. Only after validation does the program
convert them to the HID coordinate range. It does not guess coordinate units or
clamp invalid points into range.

Before real input, a second local capture is compared with the original image.
If the image changes beyond the configured threshold, the command refuses to
type. This comparison is approximate: a visually similar change or a mistaken
model location can escape detection. The program does not independently verify
focus after clicking. Inspect the behavior when first using a new screen layout.

The command subscribes to the existing video service and waits up to 15 seconds
for an HDMI signal, continuing immediately when ready. A startup timeout is not
proof of a disconnected cable. Keyframe receipt and decoding have separate
bounded waits. Only one command runs at a time using a temporary process lock;
there is no persistent lockout between attempts.

## Output and exit codes

The program emits JSON on standard output. Prompts are interactive.

| Exit | Meaning |
| --- | --- |
| `0` | Capture completed, a dry run detected an eligible login field, or input was submitted. Read `status` to distinguish these. |
| `2` | Input was refused by the recognition or image-change checks. |
| `1` | Configuration, permission, network, video, decoding, or parsing failure. |

`{"status":"submitted","login_verified":false}` means the HID requests were
accepted, **not** that the password was correct or that a desktop was reached.
A successful dry run returns `{"status":"login_detected","typed":false,...}`.

Recognition rejections include:

- `not_mac_login_page`
- `password_field_not_empty` or `password_field_uncertain`
- `low_confidence`
- `invalid_field_coordinates` or `invalid_model_output`
- `screen_changed_before_input`

When available, rejection output includes a numeric `confidence`,
`coordinate_space`, `coordinate_issue`, and a numeric coordinate pair. It does
not echo arbitrary model text. Malformed model/API responses can instead produce
a parsing error with exit code 1.

Operational errors include `api_key_not_configured`,
`tls_certificate_verification_failed`, `streamer_start_timeout`,
`streamer_http_error`, `h264_unavailable`, `video_disconnected`,
`video_frame_too_large`, `video_decode_failed`, `model_http_error`,
`model_response_too_large`, `model_response_incomplete`, `hid_http_error`, and
`hid_rejected`. HTTP failures include only the numeric status, not the response
body. A startup timeout includes the last observed `hdmi_signal` value, or null
when no boolean signal state was available. Unexpected exceptions report their
type without their message.

## Privacy and credentials

The cloud request contains one full-screen image and a fixed instruction, with
no conversation history or Mac password. The screen can contain personal
information; only run it when sending that image to DeepSeek is acceptable.
Thinking is disabled, output is capped at 160 tokens, and requests use HTTPS with
certificate validation and without environment proxy settings. Network routing
configured outside the process still applies.

Runtime configuration, credential files, screenshots, logs, backups, and the
third-party decoder are excluded from Git. Do not force-add them. Private
repository visibility does not make storing credentials appropriate.

If TLS validation fails, check `date -u` on the GLKVM and its CA certificates.
An unset clock can make a valid certificate appear not yet valid. Fix time/DNS/NTP
rather than disabling certificate checks. This program does not configure NTP.

## Resource use and validation

The Python process exits after each command. FFmpeg runs only for one-keyframe
decoding, using one thread and a bounded timeout. Original device measurements
showed about 41 MiB combined peak resident memory, including FFmpeg; these are
sample measurements, not a guarantee for other firmware or resolutions.
The verified decoder is about 30 MiB. Actual end-to-end latency also depends on
encoder startup and the model request.

The model receives the whole image, proportionally resized to fit within
768 × 432, with `detail: original`; there is no crop. Actual token use and charges
depend on the API. No accuracy percentage is promised.

Run the checks on an environment with the dependencies available:

```sh
python3 -m unittest -v test_agent
```

The tests cover recognition/schema boundaries, coordinate conversion, delayed
video startup and timeouts, model HTTP errors, password routing, key release,
and mocked one-request/one-submission behavior. They do not perform a real login.
Users have reported successful real logins on the original device; the supplied
tests do not establish compatibility with every Mac layout or GLKVM firmware.

## Update or uninstall

For an update, retain your private config and credential files, copy the new
source files, and verify the distribution checksum manifest. Stop any running
command before replacing files. If the wrapper changes, reinstall it in
`/usr/bin/mac-login`.

To uninstall, remove `/userdata/glkvm-login-agent`, `/usr/bin/mac-login`, and
`/tmp/glkvm-login-agent.lock` when no invocation is running. Removing the directory
also removes its local API key and KVM password files. No service needs disabling.
