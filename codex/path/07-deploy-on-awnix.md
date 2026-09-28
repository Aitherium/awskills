# Deploy on awnix — immutable Linux for machines where agents write software

*Chapter 7 of 9 · about 45 minutes · you need: podman (or Docker), and a terminal*

## Teach

### What "immutable" means

An immutable Linux is one where `/usr` — the folder containing all system software — cannot be changed at runtime. A traditional computer is like a notebook: you write in it, erase things, write over them. An immutable system is like a printed book: the words never change by hand, and the only way to make a new version is to print a new book and keep the old one.

Every time your agent runs code that changes the system — installs a package, updates a config, patches a binary — that change becomes a NEW IMAGE. You can compare the two, see exactly what changed, and if something went wrong you can `bootc rollback` back to the printed book you trusted.

### Cloud-init makes key-only login actually usable

An awnix machine has NO PASSWORD. Access is by SSH key only. You might think that sounds impossible — what if you lose the key? The answer is **cloud-init**: a service that runs once on first boot and injects whatever SSH keys you tell it to. On a cloud image you launched, your launch keypair arrives automatically. On bare metal you place a key yourself. Either way, nobody ever types a password, which means there is nothing to leak.

Two things must be true together or the whole idea breaks:
- **cloud-init** must run and inject the key
- **NOPASSWD sudo** must be enabled, so the account can administer the box without a password (the same setup `ec2-user` and `ubuntu` use)

### What bootc does

**bootc** — the *bootable container* system — moves a container image from `podman run` to bare metal. You build an image on your laptop, push it to a registry, and a machine boots it directly. Every boot is atomic: the system either completes or rolls back, never a partial state. An update that goes wrong is `bootc rollback`, not an afternoon of recovery.

### The aw tools are preinstalled

awnix ships 19 of the `aw*` tools ready to import: awgit (leases), awgraph (call graphs), awrelay (messaging), awseal (signing), and 15 others. Your agent does not have to install them — they are already there. That is the point of a base image: the guarantees are built in, and every agent on top gets them for free.

### Layering an agent on top

An agent is three things:
- The awnix base (immutable, atomic updates, built-in tools)
- awdk — the agent runtime
- Your skills, packs and credentials

A Dockerfile that layers on top looks like:

```dockerfile
FROM awnix:latest
RUN pip3 install --no-cache-dir awdk
# ... your packs and credentials
```

The base is read-only. Your agent runs as a service (using the unit template in the awnix repo), and when it needs a new version, you rebuild the image and `bootc upgrade`.

## Do

**1. Clone the awnix repository**

```bash
git clone https://github.com/Aitherium/awnix
cd awnix
```

You should see: the repository downloaded, a folder named `awnix` created, and your prompt now inside it.

**2. Build the image**

```bash
podman build -t awnix:latest -f Containerfile .
```

You should see: a series of `RUN` steps, each one installing packages and tools, ending with `Successfully tagged awnix:latest` (or similar).

If `podman` is not found: install podman (on Windows and macOS, this means installing Docker Desktop; on Linux, use your package manager). Or use `docker build` instead of `podman build` — the syntax is identical.

If the build fails partway through: network timeouts happen. Run the command again; the build resumes from the failed step.

**3. Verify the aw tools are inside**

```bash
podman run --rm awnix:latest awgit --version
```

You should see: a version string (like `awgit 1.2.3`), proving the tools are installed and working.

If `awgit` is not found: the build succeeded but used a different Containerfile than the one in the repo. Delete the image and rebuild from the repo root (`cd` to the folder containing `Containerfile` and rebuild).

**4. (Optional) Check bootc status**

```bash
bootc status
```

You should see: information about the image, only if you are booted from an awnix machine (a cloud instance or an ISO you burned).

If the command is not found: you are running inside a container, not booted from the image. This is expected and fine. The `bootc` command only exists on a machine that BOOTED the image; inside a `podman run` container it is absent.

Done: Run the verification command again to confirm.

```bash
podman run --rm awnix:latest awgit --version
```

You should see the same version string. Your image is built and ready to layer an agent on top (chapter 4's agent, with `FROM awnix:latest`), or to boot bare metal if you have the hardware.
