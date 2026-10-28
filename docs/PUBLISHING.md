# Package publishing

The owner publishes public, unsigned prereleases under MIT with the existing
third-party notices. Publisher signatures remain a separate future task.

## One-time account setup

### PyPI

In https://pypi.org/manage/account/publishing/ add a pending publisher (or use
the project's Publishing settings if it already exists):

| Field | Value |
| --- | --- |
| PyPI project name | `anki-x` |
| Owner | `HunterChan-SR` |
| Repository | `anki-x` |
| Workflow | `publish.yml` |
| Environment | `pypi` |

GitHub creates an OIDC identity for the `pypi` job. No PyPI password or API token
is stored in the repository. The first successful publish creates the project.

### npm

For the first publication, authenticate locally using
`npm login --registry=https://registry.npmjs.org/` and publish the verified
`anki-x-*.tgz` from the workflow's `package-channels` artifact:

```sh
npm publish ./anki-x-1.0.0-rc.2.tgz --access public --tag next --registry=https://registry.npmjs.org/
```

Complete any npm browser/2FA prompt. Then open the package's Settings at
https://www.npmjs.com/package/anki-x/access and add a GitHub Actions trusted
publisher: Owner `HunterChan-SR`, Repository `anki-x`, Workflow `publish.yml`,
Environment `npm`. Enable direct `npm publish` for unattended releases; stage-only
permission requires manual approval for each version. New trusted publisher
configurations must complete their first publication within npm's activation
window (currently two days). A later version, not an identical-version skip,
is needed to exercise the new publisher.

The workflow uses Node 24 and npm OIDC. No npm token is stored in GitHub.
Public prereleases use `next`; stable versions use `latest`.

### Homebrew

The tap is https://github.com/HunterChan-SR/homebrew-tap. A write deploy key
restricted to that repository is stored as the `HOMEBREW_TAP_DEPLOY_KEY` Actions
secret in `HunterChan-SR/anki-x`; its public half is a write-enabled deploy key
on the tap. No personal GitHub access token is used in CI. To rotate it, replace
both halves, then remove the old deploy key.

`Formula/anki-x.rb` is generated from release ZIP hashes and selects Apple
Silicon, Intel macOS or Linux x64. The tap currently follows release candidates;
it does not update Homebrew core. The formula refuses to move backwards when
an older release is retried.

## Release a version

1. Set `anki_x/__init__.py` to a new PEP 440 version. Update the default version
   in `install.sh` and `install.ps1`, README examples and release notes.
2. Commit and push the reviewed change. Push a matching tag, for example:

   ```sh
   git tag v1.0.0rc3
   git push origin v1.0.0rc3
   ```

3. `publish.yml` validates the version, calls the four-platform build and native
   install tests, builds/validates Python sdist and wheel, generates npm metadata
   and a Homebrew formula, then publishes the GitHub assets. Three independent
   jobs publish PyPI, npm and Homebrew. Inspect each job's result; success on one
   registry does not imply success on all registries.

Versions are immutable. Never move a published tag or replace an existing
release asset. PEP 440 `1.0.0rc2` maps to npm `1.0.0-rc.2`; stable `1.0.0` stays
the same. The workflow deliberately rejects unsupported version spellings.

## Retry a failed channel

Once the workflow is on the default branch, open Actions → Publish package
channels → Run workflow, enter an existing published tag, and select `pypi`,
`npm`, `homebrew` or `all`. This downloads the existing native archives and checks
their SHA-256 before preparing the channel artifacts from the tagged source.
It does not rebuild or replace native assets. PyPI skips existing files; npm
only skips an existing version if the tarball integrity matches exactly.

A tag workflow rerun that encounters an already-published GitHub release stops
before replacement. Use the channel retry path for partial publications.

## Verification

Branch/PR CI exercises application tests, npm cache/checksum/path validation,
real packed npm launchers with each native binary, Anki scheduling and native
installers. Release preparation checks wheel contents and PyPI metadata. After
publishing, verify fresh installs from each public channel. npm's first launch
requires GitHub downloads; the cached program can subsequently launch offline.

Official references: [PyPI pending publishers](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/),
[npm trusted publishing](https://docs.npmjs.com/trusted-publishers/),
[Homebrew taps](https://docs.brew.sh/How-to-Create-and-Maintain-a-Tap).
