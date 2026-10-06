# Lakad notes gold set (`notes_gold.jsonl`)

400 hand-written resident notes for scoring the two helpers that staff see next to a hazard photo: the **category hint** and the **danger flag**. It is the final exam: do not train on it, tune thresholds on it, or grow word lists from it.

## How it was written

- **Blind.** Written without opening the training notes, the lexicon or any helper code, only from the label rules below.
- **By hand.** One author (an AI model), one note at a time, in five chunks of 80 rows. No templates, no slot filling. Each chunk was checked with `schema.check` and the tests before the next.
- **Joined once.** A small script concatenated the chunks, shuffled them (fixed seed 2026, so any first-N slice is representative), renumbered ids `gd-0001`..`gd-0400` and the chunk folder was deleted.
- **Re-read.** A scan fixed the `lang` label of 14 rows whose only English was nouns, then all 400 rows were read in full. Afterwards 35 long plain rows were swapped for short ones (real notes are short) and 3 near-twins were varied. The 38 changed rows and a fresh random 60-row sample were re-read; nothing was left to change.
- Rows where two careful readers could split were left out rather than labelled.

## Row format

```json
{"id": "gd-0001", "text": "...", "lang": "en|tl|taglish", "category": "pothole|open_manhole|flooded_drain|broken_streetlight|blocked_sidewalk|other|none", "danger": true, "hard": ""}
```

`hard` names the difficulty slice for error analysis only (never a model input). There is no `family` field. Checker: `schema.py` (`check(rows, False) == []`).

## Label rules

**category** is the hazard the note describes, in any tense. If two are described, it is the one the writer calls the main or real problem ("ang pinakamalaking problema", "the main issue", "bukod sa..., ang mas malala").

| category | means |
|---|---|
| `pothole` | hole, crater, broken or sunken road surface (lubak, butas sa kalsada, buho, lungag) |
| `open_manhole` | manhole or imburnal with no cover |
| `flooded_drain` | flooding, standing water, clogged or overflowing drain or estero |
| `broken_streetlight` | dead, flickering or missing streetlight or lamp post |
| `blocked_sidewalk` | sidewalk or footpath taken by vendors, parked vehicles, construction stuff, poles |
| `other` | fallen tree or branch, exposed or hanging wire, stray dogs, garbage pile, broken traffic light or street sign |
| `none` | the note does not say what the hazard is: pleas, locations, "see photo", an accident with no cause given |

A consequence-only note ("basa na naman ako hanggang tuhod") takes the one hazard that clearly causes it; if that cannot be told, it is `none`.

**danger** is true only when the *text* describes or warns of a present risk of physical harm to people:
- someone fell, was hurt, hit, bitten or shocked, or nearly was (near miss, skid, crash);
- a child, elderly person or PWD is put at risk;
- an explicit warning ("delikado", "baka may mahulog", "someone could fall", "baka may mamatay");
- sparks or a live wire with people nearby;
- waist-deep or deeper water, or someone swept off or nearly drowned.

It is false for annoyance, traffic, smell, ugliness, delay, property damage only (tyre, rim, suspension), knee-deep or shallower water, requests and follow-ups, fixed hazards, and anything explicitly negated ("walang bata na dumadaan", "hindi naman delikado", "no one hurt"). Darkness alone ("walang ilaw", "pitch black") is false unless the note also reports a trip, fall, collision or warning. A past incident counts while the hazard is unresolved; a fixed hazard is false. A negated harm that is really a near miss ("hindi ako natumba pero muntik na") is true. **Danger follows the text, not the hazard type.**

**lang**: `en` English only; `tl` Filipino with at most borrowed nouns (manhole, sidewalk, tricycle); `taglish` clear mixing (English verbs, adjectives, phrases or clauses among Filipino words, or the reverse; affixed roots such as *na-flood* count). The 16 `other-language` rows (Cebuano 9, Ilocano 6, Hiligaynon 1) are tagged `tl` because the schema has no other slot. Typing artefacts that are not words ("Sent from my iPhone", dictated "comma") do not decide `lang`.

**hard** (one label per row, the main difficulty; `""` = no designed difficulty):

| slice | what makes it hard |
|---|---|
| `sarcasm` | ironic thanks or praise; the label is the literal hazard |
| `implicit` | the hazard is never named, only its consequence |
| `negation` | negated harm, hazard or category, including negated falls that were near misses |
| `code-switch` | heavy mid-clause Tagalog/English switching (*na-flood*, *nag-swerve*, English clauses in Tagalog syntax). Every taglish row switches; these are the 20 hardest |
| `typo` | human misspellings and texting shortcuts (lubac, manhol, drenage, kmeng) |
| `multi-hazard` | two or more hazards; the label is the one the writer calls main |
| `long` | 64-78 words, rambling, hazard buried |
| `past` | already fixed, or a past incident with the hazard still unresolved |
| `other-language` | Cebuano, Ilocano, Hiligaynon |
| `caps-rant` | ALL CAPS and exclamation marks |
| `keyboard-artifact` | device artefacts: autocorrect swaps (*nakaharap* for *nakaharang*, *binahay* for *binaha*), joined or split words, doubled words, stuck keys, stray capitals, dictation tokens, signatures |

## Counts

400 rows, 2-78 words per note (median 17; 65 rows have 10 words or fewer). 211 rows (52.8%) sit in a hard slice.

| category | rows | share | danger true | danger share |
|---|---:|---:|---:|---:|
| pothole | 82 | 20.5% | 19 | 23% |
| open_manhole | 50 | 12.5% | 28 | 56% |
| flooded_drain | 62 | 15.5% | 13 | 21% |
| broken_streetlight | 62 | 15.5% | 11 | 18% |
| blocked_sidewalk | 54 | 13.5% | 8 | 15% |
| other | 34 | 8.5% | 9 | 26% |
| none | 56 | 14.0% | 9 | 16% |
| **total** | **400** | | **97 (24.25%)** | |

| lang | rows | share | danger true |
|---|---:|---:|---:|
| taglish | 159 | 39.8% | 37 |
| tl (incl. 16 other-language) | 121 | 30.2% | 35 |
| en | 120 | 30.0% | 25 |

| hard slice | rows | danger true | en / tl / taglish |
|---|---:|---:|---|
| (plain) | 189 | 42 | 65 / 58 / 66 |
| sarcasm | 18 | 4 | 7 / 3 / 8 |
| implicit | 25 | 8 | 5 / 10 / 10 |
| negation | 20 | 5 | 7 / 6 / 7 |
| code-switch | 20 | 5 | 0 / 0 / 20 |
| typo | 20 | 3 | 6 / 5 / 9 |
| multi-hazard | 20 | 4 | 8 / 3 / 9 |
| long | 16 | 7 | 4 / 4 / 8 |
| past | 20 | 4 | 6 / 6 / 8 |
| other-language | 16 | 5 | 0 / 16 / 0 |
| caps-rant | 20 | 6 | 6 / 6 / 8 |
| keyboard-artifact | 16 | 4 | 6 / 4 / 6 |

## Known biases and limits

- **One author, one style.** Typos, slang and rants are clean imitations; real residents are messier (more emoji, voice-to-text, photo-only notes, other languages). Only 2 rows have emoji.
- **Danger tracks category.** 56% of `open_manhole` rows are dangerous against 15-26% elsewhere, so a helper that maps open manholes to danger looks good on that category. Read danger per category and per slice. It is also higher for `tl` (29%) than `en` (21%).
- **Text-only danger rule.** Many readers would call any open manhole or live wire dangerous. This set follows the note: every `open_manhole` row labelled false carries a stated non-risk reason (smell, traffic, ugliness, a barrier and light, a negation, or a fix). There is deliberately **no** "open manhole, nothing else said" row, because readers could split; helpers are untested on it.
- **Place names are decoration.** Pasong Tamo, Kalayaan, Gil Puyat and Jupiter recur; a helper must not use them as cues. Businesses (Jollibee, Mercury Drug, BDO, Rustan's) are landmarks only.
- **Other-language rows are best effort.** Written by a non-native author; labels lean on cognates (manhole, kanal, baha, lubak, buho) and clear words (suga, silaw, ubbing). Treat the slice as a robustness check, not a language test.
- **Small slices.** 16-25 rows each, so gaps under about 15 points are noise. `other` (34 rows) mixes six hazard kinds; `none` has 9 danger-true rows and `blocked_sidewalk` 8.
- **One `hard` label per row.** A typo'd sarcastic note carries only its main slice, and plain rows are not all easy: several carry smell, traffic or negation-style non-risk complaints.
- **Length.** Outside the `long` slice (64-78 words) no note exceeds 32 words, so there is nothing in between.

## 20 sample rows

| id | category | danger | lang | hard | text |
|---|---|---|---|---|---|
| gd-0260 | pothole | false | tl | - | May malaking lubak sa Pasong Tamo malapit sa tulay, ayusin niyo na po. |
| gd-0349 | open_manhole | true | taglish | - | Manhole cover missing at Kalayaan and Salamanca, tapos walang ilaw sa gabi kaya delikado sa mga dumadaan. |
| gd-0292 | open_manhole | false | en | - | The open manhole smells terrible. |
| gd-0122 | flooded_drain | true | en | - | Chest-deep flood on Evangelista, kids stranded. |
| gd-0223 | broken_streetlight | true | en | sarcasm | Great way to save electricity, switching off every lamp post on Pasong Tamo, my sister sprained her ankle in the dark on Sunday. |
| gd-0150 | open_manhole | false | taglish | sarcasm | Ang bango naman ng bukas na manhole sa tapat ng bakery, free pabango pa every morning. |
| gd-0182 | flooded_drain | false | tl | implicit | Basa na naman ako hanggang tuhod pagtawid ko sa kanto ng Gil Puyat at Makati Ave, pangatlong beses na ngayong linggo. |
| gd-0359 | none | true | tl | implicit | Muntik na maaksidente yung tricycle na sinasakyan ko kanina dito. |
| gd-0261 | pothole | true | en | negation | I did not fall off, but I almost did on that pothole along Kalayaan, it is that deep. |
| gd-0160 | open_manhole | false | taglish | negation | Walang bata na dumadaan dito and may nakapalibot naman na drum, pero wala pa ring takip ang manhole. |
| gd-0376 | none | false | en | negation | Not a pothole, not a flood, not the lights either. Just something wrong in front of our house, please check. |
| gd-0395 | open_manhole | true | taglish | code-switch | Yung manhole cover is wala na, so nag-swerve yung jeep and muntik na masagi yung mga naglalakad. |
| gd-0378 | open_manhole | true | tl | typo | walang takip yung manhol sa Valdez st, muntik ng mahulog yung ate ko |
| gd-0400 | open_manhole | true | taglish | multi-hazard | Bukod sa lubak sa tabi, ang mas malala is yung manhole na walang takip sa gitna ng kalsada, may motor na bumagsak kanina. |
| gd-0167 | blocked_sidewalk | true | taglish | long | Magandang gabi po. Ako po si Aling Cora, 68 years old, at araw-araw akong naglalakad papunta sa palengke sa Guadalupe. Dati maayos naman ang bangketa pero ngayon puno na ng mga paninda at nakaparadang motor. Dahil may arthritis ako, hindi ako makaikot, kaya napipilitan akong maglakad sa kalsada at kahapon muntik na akong mabangga ng van. Sana po ay matulungan ninyo kaming mga senior. |
| gd-0323 | open_manhole | false | tl | past | Update: nalagyan na ng takip ang manhole sa Dela Rosa, salamat po sa mabilis na aksyon. |
| gd-0372 | pothole | true | taglish | past | Last month nadapa at nasugatan yung rider sa lubak dito sa Rizal and hanggang ngayon wala pa ring ayos, ganun pa rin yung lubak. |
| gd-0353 | none | true | tl | other-language | Naay nadisgrasya dinhi ganiha, gidala sa ospital ang usa ka tigulang. |
| gd-0135 | pothole | true | tl | caps-rant | ANG LALIM NG LUBAK SA GIL PUYAT!!! NATUMBA YUNG MOTOR NG PAMANGKIN KO, DUGUAN ANG TUHOD!!! AYUSIN NIYO NA!!! |
| gd-0001 | open_manhole | true | tl | keyboard-artifact | Walang takip ang man hole sa harap ng eskwelahan baka may mahulog na bata comma pakitakpan po period |

## Using it

Report every metric overall and per `hard` slice. Keep the set frozen: if a label is wrong, fix it here with a note in the commit, never relabel to suit a helper.

```
PYTHONPATH=. python3 -c "from pathlib import Path; from models.tickets.eval.classification import schema as s; r=s.load(Path('models/tickets/eval/classification/data/notes_gold.jsonl')); print(s.check(r, False)[:10]); print(s.summary(r))"
server/.venv/bin/pytest models/tickets/eval/classification -q -p no:warnings
```
