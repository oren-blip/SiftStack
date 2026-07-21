---
name: generate-training-manual
description: Generate a personalized Lead Manager Training HTML and Word document for this customer's business. Use when user says "generate my training manual", "build my training", "make my lead manager training", "personalize the training docs", "run the training manual skill", or anything similar. Reads .datasift-config.json for their company/team info, runs find/replace on the bundled brand-standard HTML and Word templates, and outputs Lead-Manager-Training.html plus Lead-Manager-Training-Manual.docx in the working folder.
---

# Generate Training Manual

You are personalizing the brand-standard DataSift Lead Management Training for a specific customer.

**OPERATING RULES — READ FIRST:**

1. **You are running a single deterministic script. You are not authoring anything.** Do not generate HTML or DOCX yourself. Do not regenerate from markdown. Do not "improve" the layout. Do not add sections.

2. **The bundled templates are the source of truth.** `Lead-Manager-Training-Template.html` and `Lead-Manager-Training-Manual-Template.docx` are the brand-approved final designs. The skill swaps Florida Cash Real Estate / Tyler references for the customer's company / user. Nothing else.

3. **Do not read or reference the project's CLAUDE.md, TASKS.md, source MDs, or any other context file.** The only inputs are the customer's `.datasift-config.json` and the two bundled templates.

4. **Do not use the `docx` skill** or any Claude-authored docx generation. The bundled `personalize.py` handles both files.

5. **If the script fails, stop and report the error verbatim. Do not improvise.**

## Prerequisites

1. `.datasift-config.json` exists in the working folder. If missing → tell user to run `setup-my-training` first.
2. Python 3.8+ available. Test: `python3 --version`.
3. `python-docx` installed. If not: `pip3 install python-docx --break-system-packages`.

## Pre-Flight Integrity Check (MANDATORY)

Before running the script, verify it wasn't truncated during plugin extraction. This is a known issue — Cowork's zip extraction occasionally drops the tail of `.py` files.

```bash
grep -q '_FILE_COMPLETE' <plugin_path>/skills/generate-training-manual/references/personalize.py
```

- **If the grep succeeds (exit 0):** proceed to the workflow step.
- **If the grep fails (exit 1):** STOP. Tell the user:
  > "The personalize.py script was truncated during plugin installation — this is a known extraction bug. Please re-install the datasift-lead-management plugin (delete and re-add the .plugin file), then run this skill again."
  
  Do NOT attempt to patch, rewrite, or regenerate the script. The bundled version is the only correct copy.

## Workflow — Single Step

Run the bundled personalization script, pointed at the working folder:

```bash
python3 <plugin_path>/skills/generate-training-manual/references/personalize.py <working_folder>
```

The script:
- Reads `<working_folder>/.datasift-config.json`
- Find/replaces FCRE / Tyler references in the bundled HTML template using two-pass sentinel substitution (so company names that contain "Florida Cash" can never cascade into "Florida Cash Real Estate Real Estate")
- Writes `<working_folder>/Lead-Manager-Training.html`
- Find/replaces in the bundled docx template using `python-docx`
- Writes `<working_folder>/Lead-Manager-Training-Manual.docx`

Report the script's stdout to the user verbatim. If exit code is non-zero, stop and show the error.

## Verification

Both files should exist and be non-trivially sized:
- `<working_folder>/Lead-Manager-Training.html` — should be ~93–110 KB. If under 1 KB, the script failed silently.
- `<working_folder>/Lead-Manager-Training-Manual.docx` — should be ~450 KB.

```bash
ls -la <working_folder>/Lead-Manager-Training.html <working_folder>/Lead-Manager-Training-Manual.docx
```

If either is missing or the HTML is under 1 KB, stop and report. An empty/tiny HTML file usually means personalize.py was truncated — re-run the pre-flight integrity check above.

## Present to user

Use `mcp__cowork__present_files` with both files. Tell the user:

> "Your personalized training is ready.
>
> - **Lead-Manager-Training.html** — interactive 8-module training with all DataSift brand styling (flip cards, do/don't cards, pillars, callouts, SMS bubbles). Open in any browser.
> - **Lead-Manager-Training-Manual.docx** — Word document version, identical content, branded to your company.
>
> Re-run this skill anytime — it's safe (idempotent — running twice produces the same output as running once)."

## Edge Cases

- **Company name = "Florida Cash Real Estate"**: the script is a near no-op (template already has these names). It still rewrites Tyler → user_name in SMS templates.
- **python-docx not installed**: the script tells the user how to install. Don't try other libraries.
- **Working folder unwritable**: report the OS error, ask user to fix permissions.
- **User wants to edit the training**: the bundled HTML template is the source. Tyler should update it in his own folder, then re-bundle the plugin to share updates with customers.

## Do NOT

- Do not run any build script. There is no build step. The HTML is bundled as-is.
- Do not call the `docx` skill.
- Do not read source MDs (they're not even bundled in this version of the plugin).
- Do not modify the bundled templates at runtime. They're reference data.
- Do not run personalize.py multiple times in a row "just to make sure" — once is correct.
