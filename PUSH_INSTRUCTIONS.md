# Publishing spp-esxi-vib-extractor to github.com/noahfarshad

Ready to publish — sanitized, documented, licensed (stub), tested. Create it on GitHub and push.

---

## Prerequisites (one-time, you likely already have these)

```powershell
gh auth login    # if not already authenticated
git config --global user.name "Noah Farshad"
git config --global user.email "noah@essential.coach"
```

**Append the full GPL-3.0 text** (LICENSE is currently a stub). Easiest: copy from a repo you already pushed —

```powershell
cd "path\to\spp-esxi-vib-extractor"
Copy-Item "..\esxi-hpe-synergy-imagebuilder\LICENSE" ".\LICENSE" -Force
# verify it's the full ~35KB text:
(Get-Item LICENSE).Length    # expect > 30000
```

(The publish script below also auto-handles this if the LICENSE is still a stub.)

---

## Recommended: use the publish script

Drop `10_spp_esxi_vib_extractor.ps1` into your `publish-scripts\` folder (it reuses
`_helpers.ps1`), stage this repo folder into `essential_coach_public\`, then run it.
It handles LICENSE, the sanitization gate, git init/commit, repo create, push, tag,
and topics with the same paced flow as the other repos.

```powershell
cd "C:\Users\anthis\Documents\Work\essential.coach\4.23.updates\publish-scripts"
.\10_spp_esxi_vib_extractor.ps1
```

---

## Manual alternative

```powershell
cd "path\to\spp-esxi-vib-extractor"

git init
git branch -M main
git add .
git commit -m "Initial release - extract_esxi_vibs v1.0.0, Extract-EsxiVibs wrapper v1.0.0"

gh repo create noahfarshad/spp-esxi-vib-extractor `
    --public `
    --description "Extract ESXi VIBs from an HPE SPP, grouped by OS release, ready for PowerCLI Image Builder - the OS-release grouping the SPP content list doesn't give you" `
    --homepage "https://essential.coach" `
    --source . `
    --push

git tag -a v1.0.0 -m "spp-esxi-vib-extractor v1.0.0 - initial public release"
git push origin v1.0.0

gh repo edit noahfarshad/spp-esxi-vib-extractor `
    --add-topic vmware --add-topic esxi --add-topic vsphere --add-topic hpe `
    --add-topic synergy --add-topic spp --add-topic image-builder `
    --add-topic vib --add-topic python --add-topic infrastructure
```

**If `gh` isn't available**, create the repo at <https://github.com/new> (public, no README/license), then:

```powershell
git remote add origin https://github.com/noahfarshad/spp-esxi-vib-extractor.git
git push -u origin main
git tag -a v1.0.0 -m "spp-esxi-vib-extractor v1.0.0 - initial public release"
git push origin v1.0.0
```

---

## Post-push

- After pushing, **verify both refs landed**: `git ls-remote origin` should show
  `refs/heads/main` AND `refs/tags/v1.0.0`. (If a mid-run auth expiry pushed the tag
  but not the branch, run `git push -u origin main`.)
- Cut a GitHub Release for v1.0.0 with the CHANGELOG entry.
- Cross-link from the esxi-hpe-synergy-imagebuilder README (companion tool).
- Add a card to the essential.coach Automation Downloads page under "Infrastructure & Imaging".
- Mention it in the customer story (the workflow diagram already references it).
- Drop the link in the chat thread where this need came up — someone asked for exactly this.

## Verify clean before pushing

```powershell
git grep -i -E "leidos|qtc|broadcom professional" ; if ($LASTEXITCODE -eq 0) { Write-Host "FOUND MARKERS - fix" -ForegroundColor Red } else { Write-Host "Clean" -ForegroundColor Green }
```
