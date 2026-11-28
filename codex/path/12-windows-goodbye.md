# Windows Goodbye — awnix on a Windows PC, one line, no reboot

*Chapter 12 · about 15 minutes · you need: Windows 10 or 11 on x86_64, PowerShell, WSL2, about 1.5 GB of download*

## Teach

### What it is

Windows Goodbye is one PowerShell script. It installs **awnix** (the Linux under the Aither World, built on CentOS Stream 9) as its own **WSL2 distro** named `awnix`. WSL2 is the Linux virtual machine Windows already ships; a distro is one Linux system living inside it, with its own virtual disk.

"Goodbye" is the mood, not the mechanism. Windows itself is untouched. Your files, your apps and how your PC boots stay exactly as they were, and awnix runs beside them. Removing it is one flag.

The site is [goodbyewindows.sh](https://goodbyewindows.sh). The source is MIT-licensed at [github.com/Aitherium/windowsgoodbye](https://github.com/Aitherium/windowsgoodbye).

### What the script does, in order

| step | what happens | what stops it |
|---|---|---|
| 1 | checks `wsl.exe` exists and `wsl --status` answers | WSL missing: it prints the one admin command and stops |
| 2 | reads the latest release of `Aitherium/windowsgoodbye` from the GitHub API | the release has no `awnix-rootfs.tar.gz.part*` or no `SHA256SUMS` |
| 3 | downloads each part and hashes it with `Get-FileHash -Algorithm SHA256` | any part that does not match `SHA256SUMS`: nothing is installed |
| 4 | joins the parts into one `.tar.gz` in a temporary folder | |
| 5 | `wsl --import awnix %LOCALAPPDATA%\awnix\wsl <tar.gz> --version 2` | an import error, shown verbatim |
| 6 | `wsl -d awnix -- cat /etc/os-release`, then opens a shell | the distro does not start: it tells you to run `-Uninstall` |

What it never does: write a boot entry, change the boot order, reboot, install a driver, or ask for admin. `-Uninstall` is `wsl --unregister awnix`.

### Why the download is one flat file

awnix ships as a container image, which is a stack of layers. A later layer deletes a file from an earlier one with a *whiteout* entry, and turning the stack into one filesystem means applying those rules in order. Windows' own `tar.exe` cannot: NTFS cannot hold Linux symlinks, so extracting the awnix base layer on Windows silently drops thousands of files and links.

So the flattening happens once, on Linux, in the repository's release workflow: `docker export` writes the merged filesystem, the result is imported back as an image and run (it must report an OS and carry bash and systemd, or nothing is published), then it is split under GitHub's 2 GiB asset limit and hashed into `SHA256SUMS`. Your PC downloads one verified file and needs no Python and no layer logic.

### How it is tested

After every release, a workflow on GitHub's `windows-latest` machine enables WSL, runs the dry run, does the real download, checksum and import, checks that `/etc/os-release` reports an OS, then uninstalls and checks the distro is gone. One honest limit: GitHub's Windows machines cannot nest WSL2, so CI imports with `-WslVersion 1`. On your PC the default is WSL2.

### What the website does

Opening goodbyewindows.sh in a browser plays a short intro called Ignite: a classic-looking sign-in screen (it says plainly that it creates an Aitherium account and is not a Windows login), an old desktop, a stop screen in our own words, a white dot, the Aitherium mark igniting, a big bang into a nebula, then a typed boot into AitherOS in the browser. Skip and Esc jump to the end. The one-line install is on the same page.

### Limits of this version

- Windows 10 or 11 on x86_64 only, with WSL2 enabled.
- No bare-metal or dual-boot install and no Hyper-V install. For a USB stick or dual boot, the awnix ISO is on the [awnix releases page](https://github.com/Aitherium/awnix/releases/latest).
- `irm goodbyewindows.sh | iex` takes no options. To pass `-DryRun` or `-Uninstall`, download the script first (step 1 below).

## Do

**1. (Optional) Read the script and do a dry run first**

```powershell
irm https://goodbyewindows.sh/WindowsGoodbye.ps1 -OutFile WindowsGoodbye.ps1
```

You should see: a file named `WindowsGoodbye.ps1` in the current folder. Open it and read it; it is about 170 lines.

```powershell
powershell -ExecutionPolicy Bypass -File .\WindowsGoodbye.ps1 -DryRun
```

You should see: `[windowsgoodbye] Release ...: 1 part(s), ... MB to download.` and a `DRY RUN: would download ...` line. Nothing was downloaded or imported.

If it says WSL is not installed: run `wsl --install --no-distribution` once in an admin PowerShell, reboot if Windows asks, then run it again.

**2. Install**

```powershell
irm goodbyewindows.sh | iex
```

You should see: the release, each part downloading and passing its checksum, `Importing into WSL2 as 'awnix'`, then `awnix is installed.` and a Linux prompt.

If a part fails its checksum: nothing was installed. Run the command again; the download starts fresh.

**3. (Optional) Remove it**

```powershell
powershell -ExecutionPolicy Bypass -File .\WindowsGoodbye.ps1 -Uninstall
```

You should see: `Removed 'awnix'. Windows is unchanged.` This deletes the distro's virtual disk, so copy out anything you made inside it first.

Done: ask awnix what it is.

```powershell
wsl -d awnix -- cat /etc/os-release
```

You should see `NAME="awnix"` and `PRETTY_NAME="awnix (built on CentOS Stream 9)"`. Open it any time with `wsl -d awnix`.
