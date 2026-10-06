<!-- Template, not the text a rater reads. From the repo root, fill in the persona with
       models/.venv/bin/python -m models.tickets.eval.ranking.validate_ratings --instructions <persona>
     (the personas are in PERSONAS in validate_ratings.py) and give the rater that output plus a copy of
     blind_survey.json, in a folder that holds nothing else. -->
# Street hazard survey: your instructions

{persona_sentence}

You are one of several people rating the same street hazard reports from Makati, Metro Manila. Answer in that role, using what that person knows and cares about, and your own judgement. You will not see anyone else's answers.

## What you have

Two things only: these instructions and the file `blind_survey.json`, at the path the sender gave you. Open nothing else: do not read, list or search any other file or folder, and do not use the web. Everything you are allowed to know about a hazard is in its description.

`blind_survey.json` has two lists:

- `tickets`: each has an `id` (like `t017`) and a `description`, one hazard report written like a row on a city dashboard. For example: *Open manhole. Next to Robinsons Supermarket, a very busy area. 3 people reported it. Open for 1 day. Everyone agrees it is still there.*
- `pairs`: each has an `id` (like `p031`) and two ticket ids, `a` and `b`. Look the tickets up in `tickets`.

How to read a description:

- It starts with the kind of hazard.
- Then the place: the nearest known place (school, clinic, station, shop, market or bus stop) when there is one close by, and how busy the surroundings are.
- "N people reported it" is how many different people reported or confirmed it. "Open for N days" is how long the report has been open without a fix ("Reported today" means it came in today).
- "N people say it is gone" means that many people went back and said the problem is no longer there (the report is still open). "Everyone agrees it is still there" means nobody says it is gone.
- If a reporter left a note, it is quoted.

## Task 1: which first? (every pair in `pairs`)

Suppose the repair crew can fix only one of the two tickets today. Which should it fix first?

- `choice`: `"A"`, `"B"` or `"tie"`.
- `confidence`: `1` a close call, you only lean; `2` fairly sure; `3` no doubt.

## Task 2: how urgent? (every ticket in `tickets`)

Take each ticket on its own and give its `urgency`, a whole number from 1 to 5:

- `1` can wait: nothing much goes wrong if it waits a month or more
- `2` fix within a few weeks
- `3` fix within the week
- `4` fix within a day or two
- `5` fix today

Do Task 1 first, then Task 2.

## Output

Write one JSON file named `ratings_{persona}.json`, in the folder the sender gave you, in exactly this shape (the ids and values only show the shape):

```json
{
  "persona": "{persona}",
  "pairs": [
    {"id": "p000", "choice": "A", "confidence": 2},
    {"id": "p999", "choice": "tie", "confidence": 1}
  ],
  "urgency": [
    {"id": "t000", "urgency": 4},
    {"id": "t999", "urgency": 2}
  ]
}
```

Every pair id and every ticket id from `blind_survey.json` must appear exactly once, in any order: nothing missing, nothing twice, nothing invented. `choice` is exactly `A`, `B` or `tie`. `confidence` and `urgency` are whole numbers, not text. No other keys, no comments, no explanations.

## Rules

1. Judge only from the descriptions. Do not look at any other file in the repository, do not run anything to find out more about the tickets or the places, do not search the web.
2. Every answer is your own judgement as this person. Do not compute your answers: no formula, no counting or sorting by number of reports or days, no keyword rules. You may print or reformat the file to read it, for example to put the two descriptions of a pair side by side.
3. No averaging and no hedging. Do not guess what other raters or an average person would say. When you are unsure, still pick the side you lean towards and give `confidence` 1. Do not use the middle (`confidence` 2, `urgency` 3) as a safe default; use it only when it really is your view.
4. `tie` is allowed but rare: only when you honestly think the two are equally urgent and cannot say which the crew should do first. Expect it in at most about one pair in ten.
5. Treat every pair and every ticket as a new question. Do not try to make your answers consistent with each other, and do not try to even them out (for example by alternating A and B); a long run of the same letter is fine if that is what you think.
6. Answer all of them. Do not stop early or skip.

When you are done, reply with the path of the file you wrote and nothing else.
