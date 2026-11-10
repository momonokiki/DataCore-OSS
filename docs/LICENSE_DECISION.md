# Project license decision

A root-level `LICENSE` file is intentionally **not** included in this preparation package. The repository owner must choose and approve the license before public release.

## Common choices

| License | Practical effect | Typical reason to choose it |
|---|---|---|
| MIT | Short, permissive license with attribution and warranty disclaimer | Keep reuse and modification simple |
| Apache-2.0 | Permissive license with explicit patent-license terms and additional notices | Prefer explicit patent language for contributions and downstream use |
| AGPL-3.0 | Copyleft license that can require source disclosure when modified software is provided over a network | Require network-service operators to share corresponding source under its terms |

For a small, individually maintained infrastructure project that aims to encourage reuse, MIT is the simplest option. Apache-2.0 is also reasonable if its explicit patent terms are important. This is a project decision, not legal advice.

Before adding the file, decide:

1. Which license applies to DataCore's own code and original documentation?
2. Who is the copyright holder (individual, project name, or contributors)?
3. How will future contributions be licensed? A CLA is not necessary for a small project unless the owner has a specific reason to require one.

## Important third-party dependency: YomiToku

The repository snapshot pins `yomitoku==0.15.0` in the root `requirements.txt`. The upstream YomiToku project states that its source code and associated Hugging Face model weights are under **CC BY-NC-SA 4.0**, and that commercial use is handled separately. This remains true regardless of the license selected for DataCore's own code.

- Upstream project and license notice: https://github.com/kotaro-kinoshita/yomitoku
- Upstream commercial-use guideline: https://kotaro-kinoshita.github.io/yomitoku/en/commercial_use_guideline/
- CC BY-NC-SA 4.0 text: https://creativecommons.org/licenses/by-nc-sa/4.0/

Do not describe the full default dependency stack as unrestricted for commercial use. Consider making YomiToku an explicitly optional component in a later architecture change if broad commercial reuse is a goal. Also audit every direct dependency and downloaded model before publishing a container image.
