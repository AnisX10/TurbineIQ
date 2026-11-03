# GE 6B.03 public-data review for the Blender reference model

## Finding

Public GE material supports a source-noted, concept-level 6B.03 model, but it does not provide a public dimensioned general arrangement or complete component CAD. The model therefore keeps published performance and architecture facts separate from visual-only assembly proportions. It is not a reverse-engineered OEM drawing.

## Reusable public facts

| Fact | Public source | How it is used |
| --- | --- | --- |
| 45 MW simple-cycle net output; 33.4% LHV net efficiency; 10,216 Btu/kWh (10,779 kJ/kWh) LHV heat rate | [GE Vernova 2025 Gas Power catalog](https://www.gevernova.com/content/dam/gepower-new/global/en_US/downloads/gas-new-site/catalog/GEA35241-2025-GE-Vernova-Gas-Power-Catalog.pdf), 6B.03 table | Scene metadata and product reference notes. GE states ratings are net plant at ISO conditions on natural gas and actual results vary by project conditions and fuel. |
| 12.8:1 compression pressure ratio; 561°C exhaust; 145.1 kg/s exhaust mass flow | [GE Vernova 2025 Gas Power catalog](https://www.gevernova.com/content/dam/gepower-new/global/en_US/downloads/gas-new-site/catalog/GEA35241-2025-GE-Vernova-Gas-Power-Catalog.pdf), heavy-duty parameters table | Scene metadata only; not used to infer hidden geometry. |
| MS6001 family is a single-shaft machine; the published family evolution table lists 17 compressor stages and 3 turbine stages | [GE GER-4217B, Uprate Options for the MS6001](https://www.ge.com/content/dam/gepower-new/global/en_US/downloads/gas-new-site/resources/reference/ger-4217b-uprate-options-ms6001-heavy-duty-gas-turbine.pdf), especially history and evolution figures | 17 compressor stage locations, a single shaft, and three turbine stages in the visual proxy. This is family-lineage evidence, not a unit-specific 6B.03 drawing. |
| MS6001A/B has ten reverse-flow combustion chambers arranged concentrically around the compressor discharge casing | [GE GER-4217B](https://www.ge.com/content/dam/gepower-new/global/en_US/downloads/gas-new-site/resources/reference/ger-4217b-uprate-options-ms6001-heavy-duty-gas-turbine.pdf), combustion-system section | Ten can-shaped visual proxies. This is identified as family architecture; can dimensions and exact 6B.03 configuration are not asserted. |
| Public dimensions and listed masses for 6B.03 stage 1–3 nozzle and bucket-casting items | [BHEL EOI for investment cast buckets and nozzles](https://www.bhel.com/sites/default/files/EOI-Nozzle%20and%20Bucket%20Investment%20castings%20Rev-00.pdf), Annexure 1 | Bucket values are attached to one selectable bucket-casting proxy at a time. Nozzle values are shown as related stage-casting references on separately selectable illustrative vane proxies; they are not per-vane dimensions or masses. None of the proxy geometry is scaled to these values. |
| 6B.03 offered in 50/60 Hz geared configuration | [GE Vernova 2025 catalog](https://www.gevernova.com/content/dam/gepower-new/global/en_US/downloads/gas-new-site/catalog/GEA35241-2025-GE-Vernova-Gas-Power-Catalog.pdf) | A clearly illustrative gear housing is shown ahead of a generic generator. Package-specific geometry is not claimed. |

## Component envelopes from the public BHEL EOI

The EOI's Annexure 1 lists the following three-axis envelopes. The notice labels the column "Dimensions" and prints "mm" on one neighboring 9E.03 entry, while omitting the unit suffix on the 6B.03 rows; these values are interpreted as millimetres from the shared table context. The stage-part geometry in Blender is illustrative; the numbers are carried as metadata and their axis orientation is not inferred from the notice.

| 6B.03 component | Public envelope (mm) | Listed mass |
| --- | ---: | ---: |
| Stage 1 nozzle | 357 × 208 × 153 | 9.5 kg |
| Stage 2 nozzle | 361 × 280 × 170 | 19 kg |
| Stage 3 nozzle | 440 × 353 × 170 | 20 kg |
| Stage 1 bucket casting | 267 × 124 × 52 | 2.8 kg |
| Stage 2 bucket casting | 324 × 124 × 78 | 3.1 kg |
| Stage 3 bucket casting | 394 × 115 × 82 | 2.6 kg |

The BHEL notice says detailed specifications and drawings are sent to shortlisted vendors after qualification and an NDA. This model uses only the facts printed in the public EOI; it does not use vendor-only drawings, leaked manuals, copied service documents, or confidential materials. The nozzle table entry is a stage-level casting item. The individual vane meshes in the Blender scene are illustrative geometry only; the EOI does not publish their contours, count, or individual dimensions. Each bucket mesh is one illustrative bucket-casting proxy and carries the matching stage bucket-casting entry. Proxy blade counts are visual choices, not published 6B.03 counts.

## Search boundary and limitations

- Searches targeted official GE/GE Vernova product and technical publications and BHEL's public procurement site. The found public material did not include a dimensioned full-machine general arrangement, a 6B.03 assembly drawing, component contours, or a trustworthy complete set of physical envelopes.
- Search results also surfaced file-sharing copies of GE operation and maintenance manuals and a customer-specific report marked confidential. Those were excluded from the model and analysis.
- Overall length, casing diameters, internal spacing, airfoil contours, blade counts, gearbox/generator proportions, and exhaust outlet arrangement are visual proxies. Blender scene units are not physical machine dimensions.
- GE's family architecture and BHEL's part-envelope table do not establish every configuration detail for a specific installed 6B.03 unit. Variant and package differences remain possible.
- No OEM limits, maintenance thresholds, control behavior, site-specific data, or fabricated performance claims are encoded.

## Reuse decision

Use the public performance table and family-level architecture as source metadata and scene references. Show BHEL nozzle values as stage-casting references and bucket values on individual bucket-casting proxies. Build all mesh contours and the overall package layout as original, explicitly approximate geometry. Do not reuse or reconstruct restricted service-manual drawings or claim CAD/OEM dimensional accuracy.
