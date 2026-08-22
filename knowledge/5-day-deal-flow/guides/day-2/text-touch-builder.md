# Guide: text-touch-builder

> Source: https://learn.datasift.ai/text-touch-builder (Day 2 module, fetched 2026-08-21)
> Hub pages are sunset each cohort; this is the durable copy.

---

Text Touches: Warm the Number Before You Dial | DataSift Interactive Learning

-

-

-

-

-

-

-

-

    On this page

      On this page
      ×

      Pre-Call SMS

# Text Touches: Warm the Number Before You Dial

      Four short messages per record, written into the CRM. Sent before the call, never instead of it.

          12 min read

        Companion: Niche Sequential Marketing
        Companion: Phone Scoring & Spam Management

## Nobody Answers a Stranger

    An unknown number that has never contacted you is a spam risk. A number that texted yesterday about your own address is a person.

    That is the whole idea. You send one short text. The seller reads their own street address. The next ring comes from a name they have already seen. Texting first and calling second turns a cold dial into a warm one.

    The structure comes from cold email. Senders rotate slightly different copy on every send, because identical mass messages get filtered and ignored. The same rule applies to SMS, so every record gets its own wording rather than one blast template.

    Four texts pair to four call attempts. Touch 1 goes out before attempt 1, touch 2 before attempt 2, and so on to the end of the cadence. The messages live on the record itself, in four custom fields, so the caller copies the next one and dials without leaving the screen.

    The SiftStack text-touch-builder skill carries 25 handwritten variants across the four touches. Variant choice is seeded from the record's own address and owner. Neighbors never receive matching sequences, and re-running the build produces the same output.

        4

#### Custom fields

        Text Touch 1 through 4, one per call attempt, stored on the record.

        25

#### Written variants

        Seven for touch 1, six each for touches 2, 3, and 4, including no-name versions.

        160

#### Character target

        One SMS segment. The hard cap is 320, and shorter always reads more human.

        0

#### Links sent

        No links, no images, no prices. Links are the fastest way to get a number filtered.

    The Sequence

## One Job Per Touch

    Touch 1 verifies identity. Touch 2 resends. Touch 3 asks softly. Touch 4 says goodbye. The touches never combine jobs, and none of them pitch.

       |  | Touch | Job | Goes out before | Never

         | Text Touch 1 | Identity check only. Is this address yours? | Call attempt 1 | Pitches anything

         | Text Touch 2 | The drip. Not sure my text went through. | Call attempt 2 | Guilts or pressures

         | Text Touch 3 | Soft ask. Ever thought about selling, and can we talk? | Call attempt 3 | Talks price

         | Text Touch 4 | Breakup. Did you decide to keep it instead? | Final attempt | Turns negative

    Every message merges four values: the owner's first name, the street line only, the city, and the assigned caller's real first name. Every message ends in a question that takes one word to answer. The goal is a phone call, not a text conversation.

        Touch 1
        Touch 2
        Touch 3
        Touch 4

#### Identity check

        Warm, positive, and curious. You ask one question and nothing else. Seven variants ship with the skill, two of them written for records with no usable first name.

          Hi Eugene! I hope your week is going great. My name is Maria, I was looking at 714 Martha Ln and was wondering if it's yours? Thanks so much!named variant 1 of 5 · 139 characters

          Hey Eugene, I hope you are doing great! I'm not even sure I have the right number, but is 714 Martha Ln yours? Thank you! Marianamed variant 3 of 5 · 125 characters

          Hi! I hope your week is going great. My name is Maria, I'm trying to reach the owner of 714 Martha Ln. Did I get the right number? Thanks so much!no-name variant · used for entities, trusts, and initials-only owners

#### The drip

        You are not chasing. You are assuming the network dropped your message, which is a normal thing that happens to everyone. Six variants ship with the skill.

          Hi Eugene, I reached out the other day and wasn't sure my text went through. Is 714 Martha Ln your place? Maria here.named variant 1 of 4 · 115 characters

          Hey Eugene, just floating my last text back up in case it got buried. Is 714 Martha Ln your property? Thanks! Marianamed variant 4 of 4 · 113 characters

          Hey, sorry to double text! Did my message about 714 Martha Ln come through? Just making sure I have the right contact. I'm Maria.no-name variant · 127 characters

#### Soft ask

        The first mention of selling, framed as curiosity and paired with an offer to talk. No price, no offer figure, no urgency. Six variants ship with the skill.

          Hi Eugene, Maria again about 714 Martha Ln. If it's yours, have you ever thought about selling it? No pressure at all, just curious!named variant 1 of 4 · 130 characters

          Hi Eugene, this is Maria. I work with homeowners in Knoxville and I'd love to chat about 714 Martha Ln for a minute or two. Would you be open to that?named variant 3 of 4 · uses the city merge field

          Hi, Maria again. If 714 Martha Ln is one of yours, would you be open to a quick conversation about it? Happy to work around your schedule!no-name variant · 136 characters

#### Breakup

        The exit that keeps the door open. Sellers reply to this one more than you expect, because it removes the pressure entirely. Six variants ship with the skill.

          Hi Eugene, I've sent a few texts about 714 Martha Ln and haven't heard back. Did you decide to keep it instead? Either way, wishing you the best! Marianamed variant 1 of 4 · 149 characters

          Hi Eugene, I'll stop bugging you after this! Just wanted to leave my number in case 714 Martha Ln ever becomes something you'd like to talk about. Marianamed variant 3 of 4 · 150 characters

          Hi, Maria here one last time about 714 Martha Ln. If there's a better contact for that property, I'd be grateful for a point in the right direction. Thanks!no-name variant · asks for a referral instead of a sale

    Rewrite these pools in your own voice. The structure and the rules stay fixed, but the wording should sound like the person whose name signs the message. Seasonal openers work well when you regenerate the fields weekly: Monday and Friday greetings, a new month, a holiday.

## It Has to Read Like a Person

    A message that reads as machine-written is worse than no message. It kills trust on sight, and on SMS it is the fastest way to get a number reported.

      Each record pulls its own four messages out of the pool. The caller sends touch 1, then dials attempt 1.

### Nine rules that do not bend

- **One job per touch.** Verify, resend, ask, exit. Never combine two jobs in one message.

- **Short.** Aim under 160 characters, which is one SMS segment. The hard cap is 320.

- **Merge four values only.** First name, street line, city, and the sender's real first name. Use "714 Martha Ln", never the full address with the zip.

- **Positive and warm.** Hope your week is great. Wishing you the best. Never urgency, never pressure, never all caps.

- **Never name the list.** No foreclosure, probate, tax, auction, or "I know you're going through". The seller should feel found, not targeted.

- **No links, no images, no prices.** A link in a cold text is the fastest route to a filtered number.

- **Always end on a question** that takes one word to answer, usually a yes or no identity confirmation.

- **Vary the copy.** Neighboring records must never receive identical sequences. Rotate variants and keep writing new ones.

- **The goal is a phone call.** Once they reply, ask the three questions that matter, then get them on the phone.

### The tells that give it away

    The skill checks every generated message and every variant in the pools against this list, and it refuses rather than warns. Anything that trips it gets skipped and reported back to you instead of quietly shipped.

       |  | Never appears | Why it burns you

         | The em dash or en dash | The single clearest tell of machine-written text. Nobody produces one from a phone keyboard. Use a comma, a period, or the word "and".

         | Semicolons | Nobody uses a semicolon in a text message.

         | Links, emoji, ALL CAPS | Links get the number filtered. Emoji and stacked exclamation marks read as a blast.

         | Script phrases | "I hope this message finds you well", "I wanted to reach out", "circle back", "touch base", "at your earliest convenience", "no obligation".

         | Vocabulary nobody texts | Delve, navigate, landscape, streamline, robust, leverage, utilize, seamless, elevate, unlock, tailored, curated, comprehensive, holistic.

    What human actually looks like: contractions, a sentence that trails off, an apology that is not perfectly balanced. "I'm not even sure I have the right number." "Sorry to bother you." Slight imperfection reads as a person. Polished symmetry reads as a machine.

### Name hygiene

       |  | Owner value on the record | What the message uses

         | C Eugene Suthard | Eugene

         | E A Henry (initials only) | No-name variant: "the owner of 1100 Colonial Ave"

         | Suthard Family Trust | No-name variant. An entity never gets "Hi Suthard"

         | Two co-owners on the record | One name only, never both

    A message that opens "Hi E A!" tells the seller exactly what happened. Send the no-name version instead and the message still reads like a person doing research.

    Path 1

## Build It by Hand

    Five steps, no code, and one export and re-import round trip. Do this once for your ready-to-call queue and the fields stay on the records from then on.

        1

#### Create the four custom fields

          In DataSift go to Settings then Custom Fields. Add four fields of type Text to any group, and Misc. is fine: Text Touch 1, Text Touch 2, Text Touch 3, Text Touch 4. Spell the labels exactly, because the import mapping matches on them later. This is a one-time setup.

            Fig 01 · Text Touch 3 and 4 in the Misc. group, object Property, type Text. Touches 1 and 2 sit on the previous page.

        2

#### Export the target records

          Open the filter preset for the queue you are about to dial, such as your Ready to Call preset. Select all, then export to CSV. The export needs the property street address at minimum. Owner first name, city, and Assigned To make the messages noticeably better.

            Fig 02 · the Hottest 02 Ready to Call preset. Lists, tags, an investor score of 95 to 100, and named neighborhoods define the queue.

        3

#### Write the four messages per record

          Work down the rows and pick variants so that consecutive records never match. Merge in the first name, the street line, the city, and the assigned caller's first name. Apply the name hygiene rules above, keep every message under 160 characters, and build a second file with these columns.

       |  | Column | Purpose | Required

         | Property Street Address | The match key. The import upserts on address, so this must match the export exactly. | Yes

         | Property City | Helps the address match resolve cleanly. | Recommended

         | Property State | Same. | Recommended

         | Property ZIP Code | Same. | Recommended

         | Text Touch 1 | Identity check, sent before call attempt 1. | Yes

         | Text Touch 2 | The drip, sent before call attempt 2. | Yes

         | Text Touch 3 | Soft ask, sent before call attempt 3. | Yes

         | Text Touch 4 | Breakup, sent before the final attempt. | Yes

        4

#### Review before you upload

          Check three things on a sample of the file. Names render correctly and no row opens with "Hi E A". No message runs past 320 characters. Sign-offs match the caller actually assigned to that record. Then read three messages out loud, and if any sentence sounds like a brochure, rewrite the variant.

        5

#### Import back into DataSift

          Go to Upload File then Add Data and choose the **existing list** these records already belong to. That upserts by address instead of creating duplicates. Upload the file, and in the column mapping step drag Text Touch 1 through 4 onto the matching custom fields. Custom fields never auto-map, so this step is manual every time. Finish the upload.

            Fig 03 · the upload wizard. Add Data attaches to a list you already have, and Map the columns is step 4 of 5.

    **Upload one record and read it back before you release the whole file.** That single habit catches address mismatches, a mapping you dragged onto the wrong field, and a list name that would have attached nothing. Every one of those failures returns a success message.

    Path 2

## Have Claude Do It Over the API

    The same four fields and the same four messages, created and written straight onto the records. No export, no mapping screen, and it re-runs safely as the queue grows.

    You do not run any of this yourself. Open the SiftStack text-touch-builder skill inside Claude, either in the Claude Code extension for VS Code or in Claude Cowork, and tell it what you want in plain English. Claude mints the token, creates the fields, writes the messages onto every record, and reads one record back to prove the write landed. The code below is what it runs for you, and it is here so you can check the contract rather than type it.

### Step 1: tell Claude what you want

    Open a Claude session with the skill available and your DataSift login in the environment. Paste this, edit the list name, and let it work.

        Paste into Claude Code in VS Code, or Claude Cowork

          Copy

      Use the text-touch-builder skill on my DataSift account.

1. Create the four Text Touch custom fields if they are missing.
   Type text, entity property, Misc. group. Never duplicate an
   existing field.
2. Pull every record in my "Ready to Call" list.
3. Generate the four touches per record, seeded off the record so
   neighbors never match, signed by the caller in Assigned To.
4. Show me three sample records and stop. Do not write anything
   until I say go.
5. After I approve, write the values and read one record back so
   I can see the four fields populated.

Keep every message under 160 characters. Run the human-voice check
on every message and skip anything that trips it, then tell me what
you skipped and why.

### The credential that decides whether this works

    This is the step that blocks most people. DataSift runs on app.reisift.io with its API at apiv2.reisift.io, and it exposes two surfaces with different powers.

       |  | Can it | Open API key | Minted user JWT

         | Read properties, lists, tags | Yes | Yes

         | Write properties, upsert by address | Yes | Yes

         | Create or write custom fields | No | Yes

         | Expiry | Never | About 48 hours

    Custom fields do not merely return a permission error on the Open API key. They are absent from its 93-route surface entirely, so the failure arrives as a 404 that reads like a wrong URL. If you are touching custom fields, you need the minted JWT. Mint it from your own login at the start of the run, then re-mint every 30 minutes. A long job that pastes a token dies partway through. Usually that happens after it has already written half the records.

### Step 2: what Claude runs to create the fields

    The one-time schema step. It checks for each field before creating it, so re-running never duplicates anything. The group_id is required on create but is never returned by the field list, so it gets resolved from the groups route first.

        create_text_touch_fields.py

          Copy

      import json, os, time, urllib.request

BASE = "https://apiv2.reisift.io"
FIELDS = ["Text Touch 1", "Text Touch 2", "Text Touch 3", "Text Touch 4"]

def mint():
    """Never paste a token. Mint one from your own login."""
    body = json.dumps({"email": os.environ["DATASIFT_EMAIL"],
                       "password": os.environ["DATASIFT_PASSWORD"]}).encode()
    req = urllib.request.Request(BASE + "/api/token/", data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read())["access"]

def call(token, path, method="GET", body=None, override=""):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Authorization": "Bearer " + token,
               "Content-Type": "application/json"}
    if override:
        headers["x-http-method-override"] = override
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers=headers)
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read().decode()
        return json.loads(raw) if raw.strip().startswith(("{", "[")) else raw

token = mint()

# group_id is required on create and is not returned by the field list
groups = call(token, "/api/internal/custom-fields/group/?limit=999")["results"]
group_id = next(g["id"] for g in groups
                if str(g.get("title") or g.get("label")) == "Misc.")

have = {f["label"] for f in
        call(token, "/api/internal/custom-fields/?limit=999")["results"]}

for label in FIELDS:
    if label in have:
        print("exists ", label)
        continue
    made = call(token, "/api/internal/custom-fields/", "POST",
                {"label": label, "field_type": "text",
                 "entity_type": "property", "group_id": group_id})
    print("created", label, made.get("uuid"))

### Step 3: what Claude runs to write the values

    Two route details matter here. The property search is a POST that carries an x-http-method-override: GET header. Custom field values go in through a PATCH that takes field UUID and value pairs.

        write_text_touches.py

          Copy

      LIST_UUID = "paste-the-uuid-of-your-ready-to-call-list"

uuids = {f["label"]: f["uuid"] for f in
         call(token, "/api/internal/custom-fields/?limit=999")["results"]
         if f["label"] in FIELDS}

def queue(token, list_uuid, limit=200):
    """The search route is a POST carrying a GET override header."""
    out, offset = [], 0
    while True:
        r = call(token, "/api/internal/property/", "POST",
                 {"limit": limit, "offset": offset,
                  "query": {"must": {"any_lists": [list_uuid]}}},
                 override="GET")
        rows = r.get("results") or []
        out.extend(rows)
        offset += limit
        if not rows or offset >= r.get("count", len(out)):
            return out

records = queue(token, LIST_UUID)
print(len(records), "records in the queue")

for i, rec in enumerate(records, 1):
    touches = build_touches(rec)          # your four messages for this record
    pairs = [{"field_uuid": uuids["Text Touch %d" % n], "value": text}
             for n, text in enumerate(touches, 1)]
    call(token, "/api/internal/property/%s/custom-field/update-values/"
         % rec["uuid"], "PATCH", pairs)
    time.sleep(0.5)                       # about 2 requests per second
    if i % 25 == 0:
        print(i, "of", len(records))      # checkpoint, you will need it

# Read one record back before you trust the run
print(call(token, "/api/internal/property/%s/custom-field/" % records[0]["uuid"]))

### Four traps that fail quietly

       |  | Trap | What actually happens

         | Wrong credential | Every custom field write on the Open API key returns 401, and the routes are missing from its surface, so it can read like a bad URL instead of a permissions problem.

         | Pasted token | The JWT lasts about 48 hours but should be re-minted every 30 minutes inside a run. A long job dies mid-file after half the records are already written.

         | Threading the writes | The internal API throttles hard. Six threads at roughly 7 requests per second returned 429 for 529 of 740 records. Single-threaded at about 2 per second finished cleanly.

         | Using a dropdown field | A select field's value must be the option's UUID, not its label, and its options must be supplied in the same POST that creates it. Keep Text Touch fields as plain text.

### The follow-up asks worth knowing

    Once the skill is loaded, everything else is a sentence. Claude handles the column detection, the seeding, and the human-voice check, and it tells you what it skipped rather than shipping it quietly.

        More asks for the same session

          Copy

      Sign every message from Maria. The export has no Assigned To
column, so use her as the fallback signer.

The street column in this file is called "Address", not
"Property Street Address". Map it and re-run.

I rewrote the variant pools in my own voice. Audit every variant
against the human-voice rules and show me anything that trips,
before you generate a single message.

Regenerate the touches for this list with Monday openers, and
leave the identity-check structure alone.

Show me the ten longest messages you generated with their
character counts.

    Always look at samples before anything reaches a phone. Ask for three, read them out loud, and only then tell Claude to write.

      Fig 04 · Claude reporting a live run in VS Code: 175 texts queued for the day, 115 identity checks, 23 resends, 38 soft asks, 4 goodbyes.

    The Rhythm

## Run the Sequence

    The fields are useless sitting in the CRM. The value shows up when a caller sends the touch, waits a beat, and dials the same number.

       |  | Order | Caller does this | Then

         | 1 | Opens the record and copies Text Touch 1 into the texting tool | Sends it, then dials call attempt 1

         | 2 | Next contact day, copies Text Touch 2 | Sends it, then dials call attempt 2

         | 3 | Next contact day, copies Text Touch 3 | Sends it, then dials call attempt 3

         | 4 | Final contact day, copies Text Touch 4 | Sends it, then dials the last attempt

    Touches land on separate days and follow whatever call cadence your preset already runs. If your niche sequence dials Monday, Tuesday, and Wednesday, the texts go out on those same mornings ahead of the dial.

      Fig 05 · what the caller actually works from. The four touches sit on the record, and the SMS panel is one pane over.

### When they reply, stop the sequence

    A reply ends the automation. From that moment a person answers, in their own words. Three questions matter: do you have the right person, have they considered selling, and do they have a price in mind? Then get them on the phone.

      Fig 06 · a live reply. Touch 1 and touch 2 went out, Jaimin answered, and the record came back marked INTERESTED.

       |  | They say | You do

         | Yes, who's this? | Warm intro, one qualifying question, push for the call.

         | How did you get my number? | Honest and calm. You research property records for homes you are interested in, and it is fine if this is a bad time.

         | Not interested | Thank them, mark the record, and note the tone. A soft no becomes a follow-up, a hard no does not.

         | Wrong number | Apologize, thank them, and mark the phone bad so nobody dials it again.

         | STOP or hostility | Mark the number do-not-contact immediately. No reply.

### Compliance is on you

    Text from your own business number, one to one. Honor opt-outs the moment they arrive. Keep quiet hours, which means nothing before 8am or after 9pm in the recipient's local time. Texting law, including the TCPA and your state's own rules, applies to you and not to the tool. Volume texting platforms carry their own registration requirements on top of that. Personalized copy makes your messages read better. It does not make bulk texting legal where it otherwise is not.

## Where to Go From Here

    Text touches sit on top of the calling cadence you already run. These pages cover the rest of that machine.

            5-Day Deal Flow Challenge

#### Next live cohort: Monday, August 17 to August 21

          5 days live with Ty. 34 interactive modules. Save your seat in the next cohort. Already enrolled? Use this page as your between-session refresher.

        Save Your Seat

#### Niche Sequential Marketing

The staged call presets these touches attach to, plus the rotating mail sequence that runs alongside.

#### Phone Scoring & Spam Management

Score the numbers before you text or dial them. Texting a dead line wastes the touch and the attempt.

#### Cold Call Playbook

What happens after the text lands and the phone gets picked up. Opener, motivation, and the four pillars.

#### CRM Sequences

How the cadence itself is built, so the touches and the attempts stay in step as the queue grows.

        Reset All
