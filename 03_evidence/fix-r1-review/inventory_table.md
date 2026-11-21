# FIX-R1 inventory: T013 34 key files vs frozen 66502f6

| T013 path | New path (66502f6) | Status vs cfede271 | SHA-256 (66502f6) | Lines 66502f6 | Lines T013 | Pack | Key |
|---|---|---|---|---|---|---|---|
| `02_source/src/benchreceipt/capture.py` | `02_source/src/benchreceipt/capture.py` | CHANGED | `6ba926dc391412e5b3cea5e2ffd5f61c11e2922d0785bfbb43c4a208349c5f25` | 674 | 609 | 1 | yes |
| `02_source/src/benchreceipt/git_identity.py` | `02_source/src/benchreceipt/git_identity.py` | UNCHANGED | `61f1a53fae80422cf3f6d3b1cb38ac5e9814c948868c85301f590efa2792542a` | 213 | 213 | 1 | yes |
| `02_source/src/benchreceipt/ci_metadata.py` | `02_source/src/benchreceipt/ci_metadata.py` | UNCHANGED | `960ab6c537d39024e45ed213d17cef85d40eedb030876cbdeedc9e2daac0f0ac` | 196 | 196 | 1 | yes |
| `02_source/src/benchreceipt/command.py` | `02_source/src/benchreceipt/command.py` | CHANGED | `0fedd5aa4b7176e0abcf1d846e58237a30907ccff97dffe5c8dc864e7cebf276` | 289 | 228 | 1 | yes |
| `02_source/src/benchreceipt/canonical.py` | `02_source/src/benchreceipt/canonical.py` | UNCHANGED | `540d16a88e29e9ccbd1c3959c24b4c16b2a43505a48d8d8830030ae6fc147c88` | 50 | 50 | 1 | yes |
| `02_source/src/benchreceipt/verify.py` | `02_source/src/benchreceipt/verify.py` | CHANGED | `7c70f44570baf6070a1e39e8e165457e5b040f87fd3abcf31faaed3acd47cfe1` | 970 | 886 | 2 | yes |
| `02_source/src/benchreceipt/matrix.py` | `02_source/src/benchreceipt/matrix.py` | UNCHANGED | `6c2cbe8bf70c24a3e48bad10b9df84e9b19df1309a48e3caaa2a692176fe04f3` | 101 | 101 | 2 | yes |
| `02_source/src/benchreceipt/reports/junit.py` | `02_source/src/benchreceipt/reports/junit.py` | CHANGED | `bb5af528f6d98a6e9a49f164d86c6413c67234f5a5b11ba8e17fa6e8b6dd7242` | 199 | 199 | 2 | yes |
| `02_source/src/benchreceipt/reports/lcov.py` | `02_source/src/benchreceipt/reports/lcov.py` | CHANGED | `80c3f2b53b55ea98ddcd8efdcbb276754d62f6eb7273e92735dd5fb6f4612f41` | 309 | 309 | 2 | yes |
| `02_source/src/benchreceipt/bundle.py` | `02_source/src/benchreceipt/bundle.py` | UNCHANGED | `ce557f6f4ca79497be3b66ce4196ce9c7bae5b7036dc68327cabe118d0af0168` | 788 | 788 | 3 | yes |
| `02_source/src/benchreceipt/render/html.py` | `02_source/src/benchreceipt/render/html.py` | UNCHANGED | `66704da5fad44da9d15d4edef7a5580446926e1d9f92f0e50b5259ec2c9fcf63` | 693 | 693 | 3 | yes |
| `02_source/src/benchreceipt/cli.py` | `02_source/src/benchreceipt/cli.py` | CHANGED | `51fb6c3189ad8bc8776ce8fe4014984df5eb7e4425e01042d115f2f5ce1752a7` | 381 | 380 | 3 | yes |
| `02_source/src/benchreceipt/__main__.py` | `02_source/src/benchreceipt/__main__.py` | UNCHANGED | `30819d5b2ec5058171bac68f863dfb03f1d6b8858116dcca4d2eb15ea08bb278` | 13 | 13 | 3 | yes |
| `02_source/src/benchreceipt/__init__.py` | `02_source/src/benchreceipt/__init__.py` | CHANGED | `1b7920a55ec70c3c210a5b3e760054d810774d0b8d452ff59873545aba7cae44` | 10 | 10 | 3 | yes |
| `02_source/src/benchreceipt/render/__init__.py` | `02_source/src/benchreceipt/render/__init__.py` | UNCHANGED | `ddec99272b71a4193baecf2c0422118733cc3dc63e27cefa6a2895aad603489d` | 5 | 5 | 3 | yes |
| `02_source/src/benchreceipt/reports/__init__.py` | `02_source/src/benchreceipt/reports/__init__.py` | UNCHANGED | `73c8c07bffb35e8d59420d00de6911bdaf94bff086c337bf299d630daba03527` | 10 | 10 | 3 | yes |
| `02_source/src/benchreceipt/schema.py` | `02_source/src/benchreceipt/schema.py` | CHANGED | `3b0ce03abdcdbe34fdc8c66685b3cee84ba3d074192e281792a4c13517b31103` | 270 | 265 | 4 | yes |
| `02_source/src/benchreceipt/policy.py` | `02_source/src/benchreceipt/policy.py` | UNCHANGED | `683ef274cb87b8777ea04b8bb5ecf3f1dc85c81a6c9902f4dc059a8f6bf4b5e1` | 124 | 124 | 4 | yes |
| `02_source/schemas/run.v1.json` | `02_source/src/benchreceipt/schemas/run.v1.json` | MOVED+CHANGED | `fce85f3decbdcc1043df2ea852f60c7e033b5bd148d498f28704b641c7479166` | 1 | 1 | 4 | yes |
| `02_source/schemas/policy.v1.json` | `02_source/src/benchreceipt/schemas/policy.v1.json` | UNCHANGED | `2e555dc3c954b08ac70d2baeb22e449886c88e9ad5dfdc8c7f604daa5312f37a` | 1 | 1 | 4 | yes |
| `02_source/schemas/result.v1.json` | `02_source/src/benchreceipt/schemas/result.v1.json` | UNCHANGED | `2f16a1024bb589063fa89eeac9ae643b5bea52db1bee0dd73bdf1ff61f30aa11` | 1 | 1 | 4 | yes |
| `02_source/schemas/README.md` | `02_source/src/benchreceipt/schemas/README.md` | MOVED+CHANGED | `27613c955a036837bd20bb3dd2e3e9557373483a6ae49e869ab42bfb07fd4087` | 90 | 87 | 4 | no |
| `02_source/oracle/verify.mjs` | `02_source/oracle/verify.mjs` | CHANGED | `ac65f524c4fa99d601c0dad80e44e27b75d18a5d81cc4933155755219babf800` | 1823 | 702 | 5 | yes |
| `02_source/oracle/verify.test.mjs` | `02_source/oracle/verify.test.mjs` | CHANGED | `bdab56971828380b2d35f460496072756b60cdfe8784bd4a5daff6365b7c0754` | 606 | 111 | 5 | yes |
| `02_source/oracle/README.md` | `02_source/oracle/README.md` | CHANGED | `bd1e243e41e9e80e6701b2e717e25a3f2503f847fa9cd50c40ea7e232d72b4c1` | 58 | 32 | 5 | yes |
| `02_source/pyproject.toml` | `02_source/pyproject.toml` | CHANGED | `60bb4f4db82513c4103e48ed823e5d05a3014f700f7a015d795bcde651efc255` | 63 | 47 | 6 | yes |
| `02_source/examples/github-actions/ci.yml` | `02_source/examples/github-actions/ci.yml` | UNCHANGED | `9c672a4cafe9be66aac0d6b8a6849f6b90e237d0d29cf73c59c2aee37ffec7cf` | 190 | 190 | 6 | yes |
| `02_source/scripts/s0_gate.py` | `02_source/scripts/s0_gate.py` | CHANGED | `04dca6fa77e6bd684e650602ae3c6f83eb248664ae721b9c9eaadb93b878be25` | 375 | 375 | 6 | yes |
| `02_source/scripts/repeat_hash.py` | `02_source/scripts/repeat_hash.py` | UNCHANGED | `64281520c01f739a8e138804c9b9cf3aa218f7ae9b5ae31f06277aa858f94829` | 64 | 64 | 6 | yes |
| `02_source/scripts/validate_workflow_example.py` | `02_source/scripts/validate_workflow_example.py` | UNCHANGED | `8412a94c666e2edaa5fac597f3d8ff232d27a34967d7a3db73efa193fe9239bb` | 601 | 601 | 6 | yes |
| `02_source/scripts/offline_check.py` | `02_source/scripts/offline_check.py` | UNCHANGED | `3deb9b75d40088c45192c5150c98c725a6a98e27010deb7c1450c030ca45dfba` | 240 | 240 | 6 | yes |
| `02_source/scripts/performance_smoke.py` | `02_source/scripts/performance_smoke.py` | UNCHANGED | `9deb600338dfbc38edf1487c932e86ac4b078b0006a4c9a315801a1ce9b49b7c` | 165 | 165 | 6 | yes |
| `02_source/scripts/privacy_scan.py` | `02_source/scripts/privacy_scan.py` | UNCHANGED | `cdb5566b99a8cb95d7532b6bac8dde58cdffe0f3ab0b2b4a2d49eb42814d5363` | 267 | 267 | 6 | yes |
| `02_source/scripts/build_fixtures.py` | `02_source/scripts/build_fixtures.py` | CHANGED | `f6a9ff891ce2730ec41e3b86aa41cd7e12794083f89957d56f725ede05195003` | 607 | 567 | 6 | yes |
| `02_source/scripts/ui_smoke.py` | `02_source/scripts/ui_smoke.py` | UNCHANGED | `298de709d1593b1e5c802bc4b7cdae2afe30efc35cd551284b6c3797ddef907d` | 120 | 120 | 6 | yes |
| `02_source/scripts/verify_review_pack.py` | `02_source/scripts/verify_review_pack.py` | UNCHANGED | `f1c6b2d7defb6092df07e3f2d9ec8a2c2290cdf9cbcc4b7f9d3e244ec05ace03` | 253 | 253 | 6 | no |
| `02_source/scripts/check_review_coverage.py` | `02_source/scripts/check_review_coverage.py` | UNCHANGED | `70cbffe17efc8f5c311730b041cbb5d99a20eed5be1a49d9f12a5ce230d67515` | 125 | 125 | 6 | no |
