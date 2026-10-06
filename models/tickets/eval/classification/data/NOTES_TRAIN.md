# notes_train.jsonl: training notes for the category hint and the danger flag

1,500 labelled notes in 80 families, written for the two Lakad ticket helpers. Row format and checker: `../schema.py`
(`id`, `text`, `lang`, `category`, `danger`, `family`). Ids are `tr-0001`..`tr-1500`, shuffled so the id does not follow the family.

## How it was written
- By hand, family by family. A family is one scenario or phrasing pattern (for example "child nearly fell into an uncovered
  manhole near a school"). Its 15-28 notes are separate paraphrases with different words, language, length and typos. No
  templates and no word swapping.
- Written without looking at the gold set, the lexicon or any earlier evaluation material.
- Two hand passes after the first draft: one to get a realistic length mix (2-35 words) and a Tagalog/Taglish/English split
  that matches the rules below, one from cue audits (every hazard note names its hazard, no `none` note does, every danger note
  carries a risk cue, every non-danger note is negated, fixed or merely annoying).
- A light seeded pass at join time: 199 notes (30% of English, 7% of the others) get capital letter and full stop and no
  texting spellings; 155 notes get texting spellings (dto, nmn, kc, wla, tlga, lng, pls, u, thx, b4); 27 lose apostrophes; 42
  get an emoji matched to the family mood (thanks, worry, complaint). It never touches a hazard word. Typos inside hazard words
  (lubaq, mnhole, pothle, streetlite, sidwalk) are hand-written, about 25 rows.
- Checks: `schema.check` returns no problems, pytest passes, a cross-family near-copy scan finds nothing above 0.75 text
  similarity (the closest pairs are short location phrases), and two random 60-row re-reads found nothing to change.

## Label rules as applied
- **category**: the hazard the note describes, whatever the tense. Fixed reports keep their category with danger false. If two
  hazards appear, the one the writer calls the main problem. `other` = fallen tree or branch, exposed or hanging wires, stray
  dogs, garbage, broken or missing signs, traffic signals and crosswalk paint, unfinished roadwork. `none` = the hazard is not
  named (please fix asap, location only, see photo, follow-ups, "may sira po", thanks or test notes), also when the note only
  warns or reports an incident ("delikado po dito", "may nahulog dito").
- **danger**: true when the note describes or warns of present risk of physical harm: someone fell, was hurt, skidded, was
  bitten, shocked, near miss, deep water for kids, a child, elderly person or PWD at risk, an unlit hazard at night with people
  passing, "baka may mahulog". False for annoyance, traffic, smell, mosquitoes, delay, vehicle damage only, wasted electricity,
  anything fixed, and anything explicitly negated (walang bata, hindi naman delikado, no one hurt).
- **lang**: `en` has no Tagalog word and no po/opo (place names and "barangay" are fine). `tl` is Filipino with only borrowed
  nouns (manhole, sidewalk, drain, school, jeep, pothole). English verbs or adjectives, English phrases, or loan verbs with a
  Tagalog affix (nag-skid, ma-fix) make it `taglish`.
- Judgement calls: flood plus live wire is `other` (the electrical hazard is the stated danger); an unlit road is
  `broken_streetlight` and every such note names the light, lamp or pole; standing water is `flooded_drain`; a missing, broken,
  loose or stolen cover is `open_manhole`; unfinished roadwork is `other`, not `pothole`; mosquito, smell and disease worries are
  not danger; "bahay", "simbahan" and "kapitbahay" are not "baha".

## Counts
| category | rows | share | families | danger rows |
|---|---|---|---|---|
| pothole | 330 | 22.0% | 17 | 67 (20%) |
| broken_streetlight | 240 | 16.0% | 14 | 47 (20%) |
| flooded_drain | 225 | 15.0% | 12 | 32 (14%) |
| blocked_sidewalk | 210 | 14.0% | 12 | 31 (15%) |
| open_manhole | 180 | 12.0% | 10 | 48 (27%) |
| none | 180 | 12.0% | 8 | 34 (19%) |
| other | 135 | 9.0% | 7 | 46 (34%) |
| **all** | **1,500** | | **80** | **305 (20.3%)** |

| lang | rows | share | danger rate |
|---|---|---|---|
| taglish | 595 | 39.7% | 18.5% |
| tl | 453 | 30.2% | 21.6% |
| en | 452 | 30.1% | 21.5% |

Every category has at least 40 notes in each language. Families hold 15-28 notes. 19 families (305 rows) are danger, 61 are not.

Hard negatives (words that look like triggers): 271 rows (18.1%) in 16 families.
- already fixed, one family per hazard: 87 rows (naayos na yung lubak, manhole is covered now)
- explicit negation, one family per hazard: 85 rows (walang bata na dumadaan, hindi naman delikado, no one hurt)
- house lookalikes: 51 rows (bahay, bahagi, kabahayan are not baha; ilaw ng bahay is not the streetlight; house gate on the sidewalk)
- manhole mentioned but the problem is something else: 48 rows (covered manhole beside a clogged drain, manhole overflowing, manhole as landmark for a blocked sidewalk)
- 82 rows overall contain bahay, bahagi, simbahan, kapitbahay and the like.

Length: 2-35 words, median 12. 2-3 words: 17, 4-6: 248, 7-10: 384, 11-15: 498, 16-22: 241, 23-35: 112. About 84% start lowercase, 85% end
with no punctuation, 70 rows (4.7%) carry an emoji, about 25% give a time cue (kagabi, since last week, tuwing umuulan), 44% name one
of the 17 Makati streets and districts from the brief (others such as Pembo, Cembo, Bangkal, Pitogo appear too).

## Known biases
- One author in one voice. The Taglish is an approximation of Makati texting; real notes will have more slang, misspellings and
  odd phrasing, and the Tagalog here is a little more standard than people type.
- Cue heavy. Almost every hazard note names its hazard with a keyword and almost every danger note has an explicit risk word or
  event, so a keyword baseline will look good on this set. Implied risk is rare. Use the gold set to judge subtler notes.
- Category and danger are constant inside a family (a family is a scenario), so no family mixes danger labels. Within-family
  contrast comes only from the hard-negative families.
- Fixed and negated notes share a skeleton across hazards on purpose, with different words and places.
- Place names are recycled: Kalayaan, Jupiter, Magallanes, Guadalupe and Chino Roces are the most frequent.
- The generic `none` families are among the largest (20-28 notes) but inherently low variety ("please fix asap").
- Danger share is high in `other` (34%, wires and stray dogs are risk scenarios) and `open_manhole` (27%), low in flooded_drain and blocked_sidewalk (about 15%).
- flooded_drain (15%) is 1 point under the 16% aim and `other` (9%) 1 point over, because flood-with-live-wire notes went to `other`.
- English notes never carry po, which many Filipino writers add; those notes would be Taglish here.

## 20 sample rows
| id | lang | category | danger | text |
|---|---|---|---|---|
| tr-0379 | taglish | pothole | false | pothole sa Buendia fixed na 🙏 |
| tr-1247 | tl | pothole | false | walang baha pero ang daming lubak sa kalye ng aming bahay |
| tr-1123 | taglish | pothole | true | muntik kaming mabangga, iniwasan ng truck ang pothole, so scary |
| tr-1441 | en | pothole | false | Hole on the slope of the Buendia flyover entrance. Please send a crew |
| tr-0647 | taglish | open_manhole | true | open manhole sa harap ng school sa Bel-Air, kids walk there every morning, bka may mahulog |
| tr-1421 | tl | open_manhole | false | walng takip ang manhole pro walang nahulog, may harang |
| tr-0521 | taglish | open_manhole | true | muntik na akong mahulog sa manhole kagabi kasi walang ilaw, pls fix |
| tr-1231 | taglish | flooded_drain | false | barado ang drain, pls linisin 🙏 |
| tr-0422 | taglish | flooded_drain | false | umaapaw yng manhole sa Buendia whenever umuulan, baha agad, parang ilog ang daan 😤 |
| tr-0146 | tl | broken_streetlight | false | patay ang ilaw sa poste sa San Antonio pero hindi naman madilim kasi may ilaw ang mga tindahan |
| tr-1312 | tl | broken_streetlight | false | maayos ang ilaw ng bahay, ang poste sa labas ang patay |
| tr-0263 | taglish | broken_streetlight | true | estudyante uuwi ng 9pm sa Dela Rosa walang ilaw, baka may mangyari sa kanila, please repair po |
| tr-0039 | tl | broken_streetlight | true | nagkabanggaan ang dalawang motor sa madilim na kanto, patay ang ilaw ⚠️ |
| tr-0178 | taglish | blocked_sidewalk | false | nakaharang na kotse sa sidewalk, hindi dangerous, abala lang |
| tr-1211 | tl | blocked_sidewalk | true | napilitan akong bumaba sa kalsada dahil sa kotse sa bangketa, muntik akong mabangga ng bus |
| tr-0164 | taglish | other | true | nakalaylay ang wires, dangerous for kids |
| tr-1066 | tl | other | false | natumba ang puno sa kalsada, nakaharang sa isang lane |
| tr-0895 | taglish | other | false | illegal dumping nanaman sa vacant lot sa Dela Rosa, pls put a sign na bawal magtapon |
| tr-1316 | en | none | false | See photo. |
| tr-0696 | tl | none | true | opo delikado po dito |
