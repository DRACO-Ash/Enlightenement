The vendored binaries, pinned. A licence names what you may do with a file;
a digest names WHICH file. Recompute with `sha256sum design/phosphor/fonts/*.woff2`
(PowerShell: `Get-FileHash design/phosphor/fonts/*.woff2 -Algorithm SHA256`).
Fetched 29 August 2026 from the latin subset Google Fonts serves for each family.

| File | Bytes | SHA-256 |
| --- | --- | --- |
| `azeret-mono.woff2` | 26164 | `d090ca8b9080094d42b06c43f2987bfa8b36fd5565611fd59db84db53c5f74bb` |
| `saira-condensed-400.woff2` | 18160 | `56cbc482ba219469d3288028033f7d210106da182fd9c20dedf25dd3fb84f826` |
| `saira-condensed-500.woff2` | 18044 | `22c6c5bf5a71e10f0d0f71f630414437797738ed8aef613c457c749498b5e783` |
| `saira-condensed-600.woff2` | 17980 | `d20f5b8d2d6a1a236cf776fa3ac0bec671503824cbed5dedf656b61930dc87ee` |
| `saira-condensed-700.woff2` | 17808 | `eb1cf59a1f785a890ac30d69bb59fffef3989fef4e7a2ae2367c85e861077fda` |
| `saira.woff2` | 32888 | `7eb811eb14b2ee22e3fba942b25c6cd062ff050bde10d29af1a4e16f99712e17` |

Saira and Azeret Mono carry a `wght` axis spanning 100 to 900, read out of the `fvar`
table, so the ranges declared in `fonts.css` sit inside the axis rather than over it.
Saira Condensed is served upstream as static instances and carries no axis.

