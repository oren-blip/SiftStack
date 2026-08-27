# Guide: siftstack-setup

> Source: https://learn.datasift.ai/siftstack-setup (Day 3 module, fetched 2026-08-19)
> Hub pages are sunset each cohort; this is the durable copy.

---

On this page

      On this page
      ×

      Advanced AI Workflow

# The SiftStack: AI-Powered Deal Flow Automation

      From zero technical experience to a fully automated distress property pipeline.

          ~45 min setup

          Requires DataSift account

        [SiftStack on GitHub](https://github.com/tyvhb/SiftStack)
        ← Back to Challenge Hub

#### Coming from Antigravity? Read this first.

      Antigravity is being retired for this workflow. If you ran SiftStack inside Antigravity before, you do not need it anymore. Install VS Code in the steps below. The interface is nearly identical, so everything you already know still works.

      Once VS Code is installed, open the Claude Code panel and say: "Update my global CLAUDE.md to remove every Antigravity mention and switch my setup to VS Code." Claude Code rewrites your global config so every project assumes VS Code from now on. After that, you work exactly the way you did in Antigravity, just inside VS Code.

## What You're Building

    Four layers. One automated pipeline. Your computer scrapes distress property notices, enriches them with 10 data points, and uploads them to your DataSift CRM while you do something else.

#### 1. VS Code

        Your code editor

#### 2. Claude Code

        Your AI developer

#### 3. GSD Framework

        Project management

#### 4. SiftStack

        The automation engine

#### VS Code: Your Workspace

      Think of VS Code as Microsoft Word, but for code. It is where you open files, run commands, and talk to Claude Code. It is a free download and takes about two minutes to install.

#### Claude Code: Your AI Developer

      Claude Code lives inside VS Code as an extension. It can read your files, write code, run terminal commands, and manage entire projects. It is not a chatbot. It is an AI that operates directly on your computer.

#### GSD Framework: Project Management for AI

      GSD (Get Shit Done) gives Claude Code structure. It adds planning workflows, phase-based execution, verification systems, and context management. Without it, Claude Code is smart. With it, Claude Code is systematic.

#### SiftStack: The Automation Engine

      SiftStack is a Python application that scrapes distress property notices, enriches records with 10+ data points (address validation, Zillow data, skip tracing, phone scoring, obituary detection), and uploads everything to your DataSift CRM. One command. Fully automated.

#### Monthly Cost

        ~$25-160/mo depending on your API tier. Most services have free tiers to start.

#### What It Replaces

        A $500-700/mo data manager doing manual courthouse pulls, skip tracing, and CRM entry.

#### Time Investment

        ~45 minutes to set up. ~30 seconds per day to run. One command.

## Chat → Co-Work → Code

    Three tiers of Claude. You probably started at Chat. This page takes you to Code.

      1. Chat
      2. Co-Work
      3. Code

### Claude Chat: The Conversation

      You already use this. You open claude.ai, you ask a question, Claude answers. You copy-paste things in and out. It is fast for one-off tasks and thinking partner work.

        Claude Chat at claude.ai. Browser tab, text in, text out.

#### Where It Runs

Browser. You open claude.ai in a tab.

#### What It Can Do

Answer questions, write text, analyze what you paste in.

#### What It Cannot Do

Touch your files. Run commands. Do work on its own.

#### Cost

$20/mo Claude Pro. Free tier limited.

      **Best for:** research questions, writing assistance, brainstorming, quick analysis of text you paste in.

### Claude Co-Work: The Collaborator

      Claude Projects and Skills. Still in your browser, but now Claude has persistent context. You build skills (like the Comping Skill or Rehab Estimator) and invoke them on demand. Claude remembers your business, your playbooks, and your voice across every conversation in that project.

        Claude Projects with Skills loaded. Persistent context, reusable workflows, still browser-based.

#### Where It Runs

Browser. Claude Projects at claude.ai.

#### What It Can Do

Persistent memory per project. Custom Skills. Upload files. Output reusable reports.

#### What It Cannot Do

Touch files on your computer. Run scripts. Execute automations on its own.

#### Cost

$20/mo Pro works. $100/mo Max recommended for heavy skill use.

      **Best for:** repeatable analyses, comping workflows, rehab estimates, SOP generation, team playbooks. You still do the last-mile work (copy the output, paste into your CRM, trigger the next step).

### Claude Code: The Operator

      Claude inside your editor, running on your machine. Full access to your file system. Runs commands. Installs software. Builds, tests, and deploys real applications. This is the tier that lets you deploy something like SiftStack. You stop copying and pasting. Claude Code does the work.

        Claude Code inside VS Code. Lives on your machine. Touches real files. Runs real commands.

#### Where It Runs

Inside VS Code on your computer.

#### What It Can Do

Read/write files. Run terminal commands. Manage projects. Spawn subagents. Connect to MCP servers. Deploy automations.

#### What It Cannot Do

Very few limits. The boundary is the tasks your computer can perform.

#### Cost

$20/mo Pro works to start. $100/mo Max recommended for serious daily use.

      **Best for:** real automation, deploying systems like SiftStack, managing multi-file projects, running recurring data pipelines, building custom workflows end to end.

    Most people stop at Chat. A few move up to Co-Work with Skills. Almost nobody makes it to Code. That is where your edge is. The further up the stack you go, the more your AI does for you instead of with you.

## Prerequisites Check

    Make sure you have these four things before starting. Check each one off as you confirm it.

        Windows 10 or 11 computer (Mac works too with minor differences noted along the way)

        Active DataSift account (any plan: Professional, Business, Expert, or AI)

        Credit card for API signups (most services have generous free tiers)

        30-45 minutes of uninterrupted time (you can pause and resume)

    0 / 4 confirmed

### What You Will Install

       |  | Tool | What It Is | Cost

         | VS Code | Code editor (like Word, but for code) | Free

         | Node.js | JavaScript runtime (needed by Claude Code) | Free

         | Python 3.12 | Programming language (runs SiftStack) | Free

         | Git | Code downloader (gets SiftStack from GitHub) | Free

         | Claude Code | AI developer extension for VS Code | $20-100/mo

         | GSD Framework | Project management system for Claude Code | Free

         | SiftStack | The automation engine | Free (open source)

    Step 1 of 6

## Install VS Code

    VS Code is your workspace. Every tool you install after this lives inside it.

          VS Code is a code editor. Think of it as Microsoft Word, but instead of writing documents, you work with code files. You do not need to know how to code. Claude Code handles that part.

        1

#### Download VS Code

          Go to [code.visualstudio.com/download](https://code.visualstudio.com/download) and click the download button for your operating system (Windows or Mac).

            The VS Code download page. Click the big download button for your operating system.

        2

#### Run the Installer

          Open the downloaded file and follow the installer. Accept the defaults for everything. No custom settings needed.

            The installer wizard. Click Next through each screen with the default settings.

        3

#### Launch VS Code

          Open VS Code from your Start menu or desktop shortcut. You should see a welcome screen.

            VS Code after first launch. This is your new workspace.

        4

#### Quick Tour

          Three areas matter: the **file explorer** on the left (your project files), the **editor** in the center (where files open), and the **Claude Code panel** on the right (where you chat with your AI assistant). You will install Claude Code in step 3.

            The three areas: file explorer (left), editor (center), Claude Code chat (right, after install).

    Step 2 of 6

## Install Node.js, Python, and Git

    Three foundational tools. Each takes about two minutes to install. All three use simple installer wizards. You will not touch the terminal.

          **The Golden Rule.** From here until the end of this guide, you never open a terminal. You never type a command. You talk to Claude Code and it does the work. These three prerequisites use installer wizards because Claude Code needs them to exist before it can run.

        Node.js
        Python
        Git

                  Node.js lets your computer run JavaScript tools. Claude Code and GSD both need it. You will never interact with Node.js directly.

            1

#### Download Node.js

              Go to [nodejs.org](https://nodejs.org) and download the **LTS** version (the one on the left). LTS stands for Long-Term Support. It is the stable version.

                Download the LTS version (left button). Do not use the Current version.

            2

#### Run the Installer

              Open the downloaded file and accept all defaults. Click Next through every screen.

                Accept all defaults. No custom settings needed.

            3

#### Confirm It Worked

              That is it. No command typing needed. Claude Code will verify Node.js is working in a later step. If something went wrong with the installer, Claude Code will tell you and help fix it.

                "Installation complete" is all you need to see. Close the installer.

                  Python is the programming language that SiftStack is built with. SiftStack runs on Python. You do not need to learn Python. Claude Code handles the code.

            1

#### Download Python

              Go to [python.org/downloads](https://python.org/downloads) and click the big yellow "Download Python 3.12" button.

                Click the yellow download button. Any 3.12.x version works.

            2

#### Run the Installer (CRITICAL STEP)

              Open the downloaded file. **Before clicking anything else**, check the box at the bottom that says "Add python.exe to PATH". Then click "Install Now".

              **If you skip the "Add to PATH" checkbox, Python commands will not work in your terminal.** This is the number one mistake people make. If you already ran the installer without checking it, uninstall Python and start over.

                Check "Add python.exe to PATH" FIRST. Then click Install Now.

            3

#### Confirm It Worked

              When the installer says "Setup was successful" you are done. Close the installer. Claude Code will verify Python is working in a later step. If the PATH checkbox was missed, Claude Code will catch it and tell you to reinstall.

                "Setup was successful" is all you need to see.

                  Git is a download manager for code projects. It is how you get SiftStack from GitHub onto your computer. Think of GitHub as the App Store for code, and Git as the installer.

            1

#### Download Git

              Go to [git-scm.com/downloads](https://git-scm.com/downloads) and click the download for your operating system.

                Click the download for Windows (or Mac).

            2

#### Run the Installer

              Open the downloaded file. Accept **all defaults**. The installer has many screens with options. Do not change anything. Click Next through all of them.

                Accept all defaults. There are many screens. Just keep clicking Next.

            3

#### Confirm It Worked

              When the installer finishes, close it. Claude Code will verify Git is working in the first prompt you give it. No command typing on your end.

                Installer complete. Move on to the next step.

    Step 3 of 6

## Install Claude Code

    Claude Code is an extension that lives inside VS Code. Think of it as adding a super-powered assistant to your editor.

          You need a Claude subscription to use Claude Code. **Pro ($20/mo)** gets you through setup but hits token limits fast. **Max ($100/mo)** is my recommended minimum for running Claude Code at full power. Start on Pro if you need to. Upgrade to Max the moment this is how you run your business.

        1

#### Open the Extensions Panel

          In VS Code, press Ctrl + Shift + X (or click the square icon on the left sidebar). This opens the extensions marketplace.

            The Extensions panel. This is where you add features to VS Code.

        2

#### Search for Claude Code

          Type "Claude Code" in the search bar at the top. You should see the official Anthropic extension.

            Look for the official Anthropic extension. It has a blue icon.

        3

#### Click Install

          Click the blue Install button. It takes about 10 seconds. When it is done, you will see "Uninstall" and "Disable" buttons instead.

            Installed. The button changes to "Uninstall" when it is ready.

        4

#### Open the Claude Code Panel

          Look at the left sidebar of VS Code. You will see a new Claude Code icon (it looks like a small "C"). Click it. A chat panel opens on the side. This is where you will talk to Claude Code for the rest of this guide.

            The Claude Code chat panel. Type here. No terminal needed.

        5

#### Sign In

          Claude Code will prompt you to sign in. Click the "Sign in" button in the chat panel. Your browser opens. Log in with your Anthropic account. A "You're signed in" page confirms success. Come back to VS Code.

            Click Sign in, log in through the browser, you are connected.

        6

#### Give It Your First Task

          Time to verify your prerequisites. Copy this prompt into the Claude Code chat panel and press Enter:

              Say to Claude Code

            Verify that Node.js, Python, and Git are installed correctly on my computer. Report the version of each.

          Claude Code will ask permission to run some commands. Approve them. You will see it check each tool and report the versions. If something is missing, Claude Code tells you exactly what to do.

            Claude Code checking your installs. It runs the commands for you.

        7

#### Choose Your Default Mode

          Claude Code has three permission modes. Cycle them with Shift + Tab. Pick one as your default for SiftStack work.

#### Plan Mode

              Claude Code drafts a plan first, you approve, then it executes. Use this for big changes like adding a new state to SiftStack or restructuring a scraper.

#### Edit Automatically Recommended

              Approves edits without prompting but still asks for risky shell commands. The right default for daily SiftStack ops. You stay in flow.

#### Bypass Permissions

              Skips all approvals. Only use on a machine you trust for known-safe SiftStack work. Never on a shared computer.

          **Hit Shift + Tab now and select Edit Automatically.** You can change this anytime.

            The mode selector at the bottom of the Claude Code panel. Cycles with Shift+Tab.

    Hate typing long prompts? You will be giving Claude Code paragraphs of context all day. Install Wisprflow at [wisprflow.ai](https://wisprflow.ai). Hold a key, talk, paste appears. Most of you type 50 words per minute. You speak 200. Three times faster. Game changer.

## Claude Code Power Features

    You do not need to master these now. Know they exist. You will discover them as you use Claude Code.

#### Slash Commands

        Built-in shortcuts for common tasks

#### Context Management

        Keep your conversations efficient

#### Custom Skills

        Reusable AI workflows

#### MCP Servers

        Connects to external tools

#### Slash Commands

      Type / in the Claude Code chat panel to see all available commands. Key ones include: /help (see what Claude can do), /compact (save memory when conversations get long), and /clear (start fresh). Custom skills like /gsd:help appear after you install the GSD framework.

#### Context Management

      Claude Code keeps a running conversation. Long sessions burn tokens. Two slash commands save you. /compact summarizes the conversation so far and frees up token budget without losing important context. Use it after any big SiftStack operation like the install. /clear wipes the conversation entirely. Use it when switching from market research to a deployment task. The Pro plan hits limits fast without these. Max plan users still benefit from cleaner sessions.

#### Custom Skills

      SiftStack ships with six built-in skills you can call any time: Comping, Rehab Estimator, Deal Analyzer, Buyer Prospecting, Deep Prospecting, and Playbook Generator. See the Run the Skills section below for chat prompts that invoke each one. You can also build your own custom skills for county-specific quirks. See the Claude Skills for REI page for the full skill-building workflow. Skills are CLAUDE.md's portable cousin: same idea but you invoke them on demand instead of always-on.

#### MCP Servers (Model Context Protocol)

      MCP servers are plugins for Claude Code. Three useful ones for SiftStack. **Gmail MCP** lets Claude Code read incoming notice update emails from county lists. **Google Drive MCP** auto-backs up your CSV outputs to a shared Drive folder. **Google Calendar MCP** schedules courthouse trips for the in-person path. Ask Claude Code: "Add the Gmail MCP server so I can let you read my county notice subscription emails."

          **Unlock full autonomy with one flag.** By default, Claude Code stops and asks permission every time it edits a file, runs a command, or makes a change. That is safe but slow. Launch Claude Code with claude --dangerously-skip-permissions and it stops asking. Claude works end-to-end without you clicking "allow" 40 times per session. Three times faster in practice.

      You still see every change in the diff panel. You can still reject anything. You just stop babysitting.

      Launch Claude Code with --dangerously-skip-permissions once. You will never go back.

    You do not need to understand all of this to get SiftStack running. Install it, use it, and these features will start making sense within the first week. The best way to learn Claude Code is to use it on a real project.

## Your Project Brain: CLAUDE.md

    Every project can carry a CLAUDE.md file at its root. It is the first thing Claude Code reads. It teaches Claude Code your project before you type a prompt.

          Think of CLAUDE.md as the steering wheel of a ship. The smaller the steering radius, the more accurate your destination after a long journey. CLAUDE.md narrows the range of choices Claude Code makes, so over a long session it stays on course.

    SiftStack already ships with a 31KB CLAUDE.md. That is why Claude Code "just knows" how to operate the project. You did not have to explain anything. The file did it for you.

    The best part: you can edit it. Add your own permanent context. County defaults, your phone number for alerts, your preferred Slack channel, your operating cadence. Once it is in CLAUDE.md, Claude Code remembers it across every future conversation.

        Say to Claude Code

      Open the CLAUDE.md file at the root of my SiftStack project. Add a section at the bottom called "My Defaults" with these preferences: my primary county is [YOUR COUNTY], send daily summaries to my [Slack/Discord], my preferred run time is [TIME], my dispositions go to [DataSift list name]. Save the file.

      SiftStack's CLAUDE.md open in VS Code. This is the brain Claude Code reads first.

    Skills (covered in the previous section) are CLAUDE.md's portable cousin. Same idea, but you invoke them on demand instead of always-on.

          **Refresh the brain. Start fresh sessions.** Every couple weeks, ask Claude Code: "Review our recent conversations and update CLAUDE.md and your memory files with anything new I should remember. County quirks, disposition rules, run times, preferences." Claude writes it in. Next session starts smarter.

      Then do the other half: **stop running one endless conversation**. Long sessions get slow and sloppy. When a task finishes, type /clear or open a new chat. Claude reloads CLAUDE.md fresh. Performance stays sharp. Your token budget stretches further.

    Step 4 of 6

## Install the GSD Framework

    GSD (Get Shit Done) gives Claude Code structure. It adds planning workflows, verification systems, and context management. Without it, Claude Code is smart. With it, Claude Code is systematic.

        1

#### Ask Claude Code to Install GSD

          In the Claude Code chat panel, paste this prompt:

              Say to Claude Code

            Install the GSD (Get Shit Done) framework globally on my machine and configure the hooks so it runs automatically with every Claude Code session. When you are done, confirm that I can use the /gsd:help command.

          Claude Code will ask permission to run the install. Click Approve. It handles the npm install, sets up the hooks in your settings, and verifies everything works. You watch it happen.

            Claude Code running the install. No commands typed by you.

        2

#### Test It

          In the Claude Code chat panel, type this and press Enter:

              Say to Claude Code

            /gsd:help

          You should see a list of available GSD commands. There are over 60 of them. You will not use most right away.

            The GSD help menu appears. You are fully set up.

### Key GSD Commands

    You do not need to memorize these. Claude Code knows them. Ask Claude Code "how do I start a new project with GSD?" and it will guide you.

      Project Setup

        /gsd:new-project starts a new project with deep context gathering. /gsd:progress shows where you are. /gsd:health checks your project setup for issues.

      Planning + Execution

        /gsd:plan-phase creates detailed plans for a work phase. /gsd:execute-phase runs the plan. /gsd:verify-work validates that everything was built correctly. /gsd:autonomous runs all phases back-to-back with no intervention.

      Debugging + Quality

        /gsd:debug starts a systematic debugging session. /gsd:validate-phase audits completed work. /gsd:ship creates a pull request and prepares for deployment.

    Step 5 of 6

## Clone and Configure SiftStack

    Now for the main event. You are going to download SiftStack from GitHub and set up its Python environment.

          This step installs a lot of things: the code from GitHub, a "virtual environment" (like a clean room for SiftStack's tools), 18 Python packages, and a Chromium browser for web scraping. You are not going to do any of that manually. One prompt to Claude Code handles all of it.

        1

#### Ask Claude Code to Clone and Set Up SiftStack

          Open the Claude Code chat panel. Paste this prompt:

              Say to Claude Code

            Clone the SiftStack repository from https://github.com/tyvhb/SiftStack to my Desktop. Then set it up: create a Python virtual environment in the project folder, install all the dependencies from requirements.txt, and install the Playwright Chromium browser. When you are done, open the project in a new VS Code window and confirm everything is ready.

          Claude Code will ask permission for each step. Click Approve each time. You will watch it clone, create the virtual environment, install 18 Python packages, and download the Chromium browser. Total time: 3-5 minutes depending on your internet speed.

              Claude Code cloning and setting up the project.

              Dependencies installing. Watch it go.

          After this big install finishes, type /compact in Claude Code. SiftStack's setup eats a lot of tokens. /compact summarizes the conversation so you do not burn your Pro plan limit on the next prompt.

        2

#### Confirm SiftStack Is Ready

          When Claude Code reports "everything is ready", you are set. A new VS Code window opened with SiftStack in the file explorer on the left. The src/ folder contains all the Python code. A .venv folder (hidden) contains the virtual environment. A .env.example file is the template for your API keys.

            SiftStack ready. You will fill in the .env file in the next section.

    Step 6 of 6

## Configure Your API Keys

    Each service needs an API key (a password that lets SiftStack talk to it). Open each accordion below and follow the signup steps.

        1

#### Ask Claude Code to Create Your .env File

          In the Claude Code chat panel, paste this prompt:

              Say to Claude Code

            Create a .env file in my SiftStack project by copying the .env.example template. Then open it in the editor so I can fill in my API keys.

          Claude Code creates the file and opens it in the main editor area. You will see a list of variables like TNPN_EMAIL= with empty values after the equals sign. You fill these in as you create accounts in the steps below.

            The .env file. Paste your real API keys next to each variable.

    **Never share your .env file with anyone.** It contains all your passwords and API keys. It is already listed in .gitignore so it will never be uploaded to GitHub.

### Required Services Required

    You need these three to run the basic scraping pipeline.

      Public Notice Site Account (Free)

        SiftStack scrapes your state's public notice website. For Tennessee, go to [tnpublicnotice.com](https://www.tnpublicnotice.com) and create a free account.

        In your .env file, set:

        TNPN_EMAIL=your-email@example.com
TNPN_PASSWORD=your-password

          Create a free account on your state's public notice site.

      2Captcha (~$3/mo)

        Public notice sites use CAPTCHA puzzles to block automated access. 2Captcha solves them for you. Go to [2captcha.com](https://2captcha.com), create an account, and add $3 of credit. This lasts about a month at typical usage (30 notices/day).

        In your .env file, set:

        CAPTCHA_API_KEY=your-2captcha-api-key

          Your API key is on the dashboard after you sign up and add credit.

      DataSift Login (Your existing account)

        SiftStack uploads enriched records directly to your DataSift CRM. Use the same email and password you log in to DataSift with.

        In your .env file, set:

        DATASIFT_EMAIL=your-datasift-email
DATASIFT_PASSWORD=your-datasift-password

          Use the same credentials you log in with at datasift.ai.

### Recommended Services Recommended

    These enrich your data significantly. The pipeline works without them but produces less useful records.

      Anthropic API Key (~$2/mo)

        SiftStack uses Claude Haiku (the fast, cheap model) to parse complex notices and detect obituaries. Go to [console.anthropic.com](https://console.anthropic.com), create an API account (separate from your Claude chat subscription), and generate an API key.

        In your .env file, set:

        ANTHROPIC_API_KEY=sk-ant-your-key-here

          Generate an API key in the Anthropic Console. Starts with "sk-ant-".

      Smarty Address Validation (Free 250/mo)

        Smarty validates and standardizes addresses via the USPS database. Catches typos, adds zip+4, and geocodes. Go to [smarty.com](https://www.smarty.com) and create a free account. The free tier gives you 250 lookups per month.

        In your .env file, set:

        SMARTY_AUTH_ID=your-auth-id
SMARTY_AUTH_TOKEN=your-auth-token

          Find your Auth ID and Auth Token on the Smarty dashboard.

      Trestle Phone Scoring ($0.015/phone)

        Trestle scores phone numbers 0-100 for activity. Eliminates ~50% of dead numbers before you dial. Go to [trestleiq.com](https://trestleiq.com) and create an account.

        In your .env file, set:

        TRESTLE_API_KEY=your-trestle-key

          Your API key is in the Trestle dashboard settings.

      Tracerfy Skip Trace ($0.02/record)

        Tracerfy finds phone numbers and emails for property owners. Go to [tracerfy.com](https://tracerfy.com) and create an account.

        In your .env file, set:

        TRACERFY_API_KEY=your-tracerfy-key

          Find your API key in the Tracerfy account settings.

      Slack or Discord Notifications (Free)

        Get daily summaries and error alerts sent to Slack or Discord. Create a webhook URL in your workspace settings.

        In your .env file, set:

        SLACK_WEBHOOK_URL=https://hooks.slack.com/services/your-webhook

        **Discord users:** Use your Discord webhook URL and add /slack at the end.

          Create a webhook in your Slack or Discord channel settings.

### Optional Services Optional

    These add extra enrichment. Skip them for now and add them later when you need more data.

      OpenWeb Ninja: Zillow Data (Free 100/mo)

        Pulls Zestimate, MLS data, equity, and property photos from Zillow. Free tier: 100 lookups/month. Set OPENWEBNINJA_API_KEY in your .env file.

      Serper.dev: Google Search (Free 2,500 queries)

        Powers the obituary and entity research features. Free tier: 2,500 queries. Set SERPER_API_KEY in your .env file.

      Firecrawl: JS Page Scraping (Free 500 pages)

        Scrapes JavaScript-rendered pages for deeper research. Free tier: 500 pages. Set FIRECRAWL_API_KEY in your .env file.

      Ancestry.com: SSDI + Obituary ($29/mo)

        Automates Social Security Death Index lookups and obituary collection. Requires World Explorer subscription. Set ANCESTRY_EMAIL and ANCESTRY_PASSWORD in your .env file.

## Configure Your Market Data Sources

    I built SiftStack on Knox County, Tennessee. That is not where you live. Every state publishes distress data differently: clean portals, scanned PDFs, or nothing digital at all. Claude Code researches your market and adapts SiftStack to match.

          This is the step most people skip. They fire up SiftStack with Knox defaults, nothing happens, and they give up. Do not be that person. Spend 20 minutes here. Claude Code does the hard work. You answer questions about where you operate.

### Phase 1: Research Your Market

    Your first task with Claude Code inside SiftStack. Paste this prompt. Fill in your actual state and county:

        Say to Claude Code

      Research how distress property notices are published in [YOUR COUNTY], [YOUR STATE]. Cover all six notice types: foreclosures, probates, tax sales, tax delinquencies, evictions, and code violations. For each type, find: (1) the primary source (online portal, newspaper, courthouse, county clerk PDF), (2) the URL if online, (3) whether it is scrapable programmatically, and (4) the approximate publishing cadence. Spawn parallel subagents to research each notice type at the same time, one agent per notice type, then synthesize the results into a single summary table.

    Claude Code spawns six subagents at once, one per notice type, all researching in parallel. You get the full picture in 2-3 minutes instead of 15.

### Phase 2: Pick Your Data Paths

    Most counties have a mix of sources. You will probably need two or three of the paths below. Claude Code will tell you which ones based on Phase 1 research. Each tab below walks you through setting up one path.

        Online Portal
        Monthly PDFs
        Courthouse In-Person

#### When to Use This Path

        Your state or county publishes notices on a website you can log into (like Tennessee's tnpublicnotice.com, Florida's myfloridalegal.com portals, or individual county clerk websites). This is the easiest path because SiftStack can run fully automatically.

#### What You Get

- Daily automated scraping

- First-to-market timing (pull notices within hours of publication)

- Zero manual work

#### Configure It

        Paste this prompt into Claude Code:

            Say to Claude Code

          Based on my Phase 1 research, my primary online portal is [PORTAL URL]. The account credentials are in my .env file. Adapt SiftStack's scraper configuration to pull from this portal for my county. Update the saved searches to match my county and notice types. Then run a test scrape of the last 7 days so we can verify it works.

        Claude Code updates the config.py file, adjusts the scraper to your portal's structure, and runs a test. If the portal blocks something, Claude Code tells you exactly what it needs (a different login method, CAPTCHA type, or filter).

#### When to Use This Path

        Your county publishes notices as downloadable PDFs. Tax sale lists and probate dockets often work this way. The county clerk's website has a link, you click it monthly, you get a scanned PDF back. SiftStack can OCR these PDFs and extract the data automatically.

#### What You Get

- Automated OCR extraction from scanned PDFs

- Full enrichment pipeline on the extracted records

- Monthly cadence (most PDFs publish monthly)

#### Configure It

        Download the PDF from your county's website and save it to your SiftStack folder. Then paste this prompt:

            Say to Claude Code

          I saved a tax sale PDF to the project folder: [FILENAME.pdf]. Run SiftStack's pdf-import command to OCR it and extract the records. Use [YOUR COUNTY] as the county and [NOTICE TYPE] as the type. Show me the first 10 records so I can verify the extraction worked.

        When the extraction looks good, ask Claude Code to run the full enrichment pipeline and upload to DataSift. Set a calendar reminder to pull the PDF each month.

#### When to Use This Path

        Some counties have nothing digital. The notices only exist on paper at the county clerk's office, or on a public terminal inside the courthouse. You photograph the terminal screen (or the paper docket), upload the photos, and SiftStack OCRs them into records. This is the first-to-market edge because almost no one else does this.

#### Two Ways to Get the Photos

#### You Go

            Once a week, drive to the courthouse. Photograph the probate docket board, foreclosure postings, and tax sale notices on the public terminal. Takes 30-45 minutes per visit.

#### Hire Someone

            Post a task on TaskRabbit or Craigslist. $25-50/hr for someone to photograph the courthouse data once a week. Send them the list of screens to capture. See the First-to-Market Data page for the exact delegation workflow.

#### Configure It

        Drop your photos into a folder called courthouse_photos inside SiftStack. Then paste:

            Say to Claude Code

          I have courthouse photos in the courthouse_photos folder. Run SiftStack's photo-import command. Use [YOUR COUNTY] as the county and [probate/foreclosure/tax_sale/eviction] as the notice type. Show me any photos that were too blurry to OCR so I can reshoot them.

        **Optional upgrade:** Set up a Dropbox folder. Point your helper's phone at it. Photos sync automatically. SiftStack watches the folder and processes new photos in the background. Zero manual upload work.

### Phase 3: Set Your Cadence

    Once your paths are configured, decide how often SiftStack runs. Pick the cadence that matches your data source:

       |  | Path | Cadence | Why

         | Online Portal | Daily | New notices publish continuously. Same-day pulls win the speed race.

         | Monthly PDFs | Monthly | PDFs only update once a month. Running more often wastes your time.

         | Courthouse Photos | Weekly | Weekly courthouse visits balance freshness with the operational effort of going.

    Whatever path you end up on, the goal is the same: pull your county's distress data before anyone else can. The online portal is the easiest. Courthouse in-person is the most defensible because nobody else bothers. Do what your market allows. Then optimize.

## Your First Run

    Everything is installed. Your market is configured. Time to run the pipeline and watch it work. The examples below use Knox County as a placeholder. Replace it with whatever county you configured in the previous section.

      The daily pipeline as a belt: every notice gets stamped at scrape, tagged at enrich, boxed as CSV, and the bell rings in Slack when the run finishes.

        1

#### Ask Claude Code to Run Your First Scrape

          In the Claude Code chat panel, paste this prompt (swap "Knox" for your own county):

              Say to Claude Code

            Activate the SiftStack virtual environment and run a daily scrape for [YOUR COUNTY]. Show me the output as it runs so I can see what is happening.

          Claude Code activates the virtual environment for you, then starts the scrape. You watch it log in to the public notice site, solve CAPTCHAs, and pull down each notice in real time.

            SiftStack logging in and scraping. Claude Code runs it for you.

        2

#### Watch the Enrichment

          As each notice comes in, SiftStack enriches it: standardizes the address, pulls Zillow data, runs skip tracing, scores phone numbers, checks obituaries. You do not do anything. Each enrichment service you configured in your .env file runs automatically.

            Each notice is scraped, parsed, and enriched in sequence.

        3

#### Review the Results

          When the run finishes, Claude Code will tell you how many records were processed and where the CSV file is saved. Ask it to open the file for you:

              Say to Claude Code

            Open the output CSV file from that run and show me the first 10 records.

            The enriched records. You can also open the file in Excel.

        4

#### Run the Full Pipeline

          Now for the real deal. Upload to DataSift and notify Slack automatically:

              Say to Claude Code

            Run the full SiftStack daily pipeline for [YOUR COUNTY]. Upload the results to DataSift and send me a Slack summary when done.

          Claude Code runs the scrape, enriches everything, uploads records to your DataSift CRM, triggers SiftMap and skip tracing inside DataSift, and delivers a summary to Slack/Discord.

              Records uploading to DataSift automatically.

              Daily summary delivered to your Slack/Discord.

        5

#### Verify the Run Quality

          Do not trust automation blindly. Ask Claude Code to inspect what just happened and report any silent failures.

              Say to Claude Code

            Verify today's SiftStack run was successful. For each record, confirm the address was standardized, phone numbers were scored if Trestle is configured, and the DataSift upload succeeded. Report any records that failed each step and explain why.

          The first 2 weeks, verify every run. After that, verify weekly. Catch the silent failures before they cost you a deal.

    Run this once a day. One prompt to Claude Code. Done. Set a reminder on your phone for 8 AM. Open VS Code, ask Claude Code to run the daily pipeline, close the laptop. You have leads no one else has yet, delivered before your coffee.

### What Just Happened

#### 1. Scraped

        Logged in, solved CAPTCHAs, extracted every new distress notice from the public notice site.

#### 2. Enriched

        Standardized addresses, pulled Zillow data, ran skip tracing, scored phone numbers, checked obituaries.

#### 3. Uploaded

        Formatted as a 41-column DataSift CSV, uploaded to your CRM, triggered SiftMap enrichment and skip tracing.

#### 4. Notified

        Sent a daily summary to Slack or Discord with record counts, errors (if any), and run duration.

## Schedule It

    The real win: SiftStack runs on its own schedule and you check Slack for the daily summary. Three ways to set that up. Pick whichever matches your comfort level.

          Claude Code can set up any of these for you. You do not need to know the underlying tools. You pick a path below and paste the chat prompt. Claude Code handles the rest.

        Apify (Easiest)
        GitHub Actions (Free)
        Modal (Advanced)

#### Apify Actor: Easiest, ~$5/mo

        SiftStack already ships with Apify support. The .actor/ folder in the repo is the deployment manifest. Push to Apify, configure your secrets in the Apify dashboard, set a cron schedule, done.

#### Pros

Easiest setup. Built-in monitoring. No GitHub knowledge needed. Works out of the box with SiftStack.

#### Cons

$5/mo minimum. Less flexible for custom triggers later.

            Say to Claude Code

          Deploy SiftStack to Apify and configure it to run daily at 6 AM Eastern. Walk me through creating an Apify account if I do not have one, and help me copy my secrets from my .env file into Apify's secret store.

          SiftStack running on Apify with a cron schedule.

#### GitHub Actions: Free, more setup

        GitHub Actions runs your code on GitHub's servers on a schedule. Free for public repos. Requires you to fork the SiftStack repo into your own GitHub account first.

#### Pros

Free. Version controlled. Easy to inspect run history. No vendor lock-in.

#### Cons

Requires a GitHub account and one-time fork setup. Secrets management is slightly clunkier than Apify.

            Say to Claude Code

          Set up a GitHub Actions workflow that runs SiftStack daily at 6 AM Eastern. The workflow should pull from my forked repo, install dependencies, run the daily pipeline, and notify Slack on success or failure. Walk me through forking the SiftStack repo to my GitHub account if I have not done that yet.

          GitHub Actions workflow history showing successful daily runs.

#### Modal: Serverless, advanced

        Modal.com gives you serverless Python execution with cron triggers. Free tier covers daily runs. Best for advanced users who want webhook triggers, retry logic, or custom monitoring later.

#### Pros

Most flexible. Free tier. Easy to add webhooks, retry logic, and event-based triggers later.

#### Cons

More concepts to learn. Overkill for simple daily runs. Requires Modal account setup.

            Say to Claude Code

          Deploy SiftStack to Modal as a scheduled function. Set it to run daily at 6 AM Eastern with retry logic if it fails. Walk me through Modal account setup if needed.

          Modal dashboard showing the scheduled SiftStack function.

    Pick Apify if you want the fastest path. Pick GitHub Actions if you want it free and you are comfortable with one-time GitHub setup. Pick Modal if you plan to grow into custom webhook triggers and event-based runs.

## Run the Skills

    SiftStack ships with six callable skills. Pull a comp on a hot lead. Estimate a rehab. Run a market analysis. Generate an SOP for your VA. All from the same VS Code window.

          You do not need to remember any commands. You ask Claude Code in plain English: "run a comp on 123 Main St." Claude Code knows which SiftStack skill to invoke and how to format the call. The output appears in your project folder as Excel files, PDFs, or CSVs depending on the skill.

### Available Skills

      Comping Workflow: ARV in 60 seconds

        The Two-Bucket comping methodology. Pulls comparable sales, separates renovated from unrenovated, applies adjustments, returns a calibrated ARV with a 7-tab Excel report. Works on disclosure and non-disclosure states.

            Say to Claude Code

          Run a comp on [PROPERTY ADDRESS]. Save the report to my output folder and walk me through the ARV calculation.

        **Full walkthrough:** Comping Workflow page

      Rehab Estimator: room-by-room cost

        4-tier finish-grade estimator. Inputs property condition, square footage, and finish tier. Outputs a 9-tab Excel workbook with full rehab budget, wholetail option, deal analyzer, and project timeline. Calibrated to your local market.

            Say to Claude Code

          Run a rehab estimate on [PROPERTY ADDRESS] at finish tier 3 (investor flip grade). I can send you photos if you have them in the project folder.

        **Full walkthrough:** Rehab Estimator page

      Deal Analyzer: MAO, ROI, financing scenarios

        Combines the comp + rehab outputs with your purchase price assumptions to calculate Max Allowable Offer, ROI, profit margins, and financing scenarios for both hard money and conventional. Returns a side-by-side Excel comparison.

            Say to Claude Code

          Analyze the deal at [PROPERTY ADDRESS] assuming a $[PURCHASE PRICE] purchase. Use the comp and rehab estimates already in my output folder. Show me MAO and ROI for both hard money and conventional financing.

      Buyer Prospecting: find cash buyers in your market

        Identifies recently active cash buyers in your target market. Pulls investor transactions from the last 12 months, filters by buyer type (fix-and-flip, buy-and-hold, wholesaler), enriches with portfolio data. Output is a verified buyer list ready for outreach.

            Say to Claude Code

          Find me the top 50 active cash buyers in [YOUR COUNTY]. Focus on fix-and-flip buyers who have closed at least 3 deals in the last 12 months. Save the list to my output folder.

        **Full walkthrough:** Buyer Prospecting page

      Deep Prospecting: 4-level research framework

        Goes beyond skip tracing. Layers L1 enhanced skip trace, L2 public records, L3 genealogy (Ancestry, FindAGrave, obituary search), and L4 expert services. Returns a research pack PDF with verified contact info, heir mapping, and decision-maker identification. Best for high-value distressed properties where you need to find someone the easy tools missed.

            Say to Claude Code

          Run a deep prospecting research pack on the records in [output/your-csv.csv]. Use depth level 3 (include genealogy and obituary search). Save the PDF reports to the output folder.

        **Full walkthrough:** Deep Prospecting page

      Playbook Generator: SOPs and scripts on demand

        Generates standard operating procedures, call scripts, and training materials for your team. Pick a blueprint (wholesale, novation, buy-and-hold, creative finance) and a market context. Outputs a polished playbook ready to hand to a new VA or caller.

            Say to Claude Code

          Generate a wholesale playbook for [YOUR MARKET]. Include lead intake scripts, qualification criteria, and a step-by-step process my caller can follow.

        **Full walkthrough:** SOP Creation page

    The comping skill replaces a $30/comp manual workflow: run one on every hot lead. The rehab estimator replaces a contractor walk-through for first-pass triage. The buyer prospecting skill builds a cash buyer list in 10 minutes that would take a VA two days.

## What Claude Code Runs For You

    For the curious. These are the commands Claude Code executes when you ask it to do things. You never type them yourself.

          Everything below happens automatically when you talk to Claude Code. "Run a comp on 123 Main St" becomes the first command. "Upload everything to DataSift" adds the right flag. You describe what you want. Claude Code builds the command. This reference is here so you understand what it is doing, not so you memorize anything.

        Data Acquisition
        Deal Analysis
        CRM Operations
        Workflow

        # Scrape new notices since last run
python src/main.py daily --counties Knox

# Scrape last 12 months of notices
python src/main.py historical --counties Knox

# Import notices from scanned PDF
python src/main.py pdf-import --pdf-path FILE --pdf-county Knox

# Import notices from courthouse photos
python src/main.py photo-import --folder DIR --photo-county Knox --photo-type probate

# Auto-watch Dropbox for new photos
python src/main.py dropbox-watch

# Re-import and re-enrich existing CSV
python src/main.py csv-import --csv-path FILE

        # Run comp analysis on a property
python src/main.py comp --address "123 Main St"

# Generate rehab estimate
python src/main.py rehab --address "123 Main St" --tier 2

# Full deal analysis (MAO, ROI, financing)
python src/main.py analyze-deal --address "123 Main St" --purchase-price 150000

# Market analysis for a county
python src/main.py market-analysis --counties Knox

# Find cash buyers in your market
python src/main.py buyer-prospect --counties Knox

# Deep prospecting on a list
python src/main.py deep-prospect --csv-path output/records.csv --depth 3

        # Discover and manage CRM presets
python src/main.py manage-presets --discover

# Download sold property data
python src/main.py manage-sold --months-back 12

# Score phone numbers with Trestle
python src/main.py phone-validate --list-name "Foreclosure"

# Auto-qualify leads (4 Pillars)
python src/main.py lead-manage --lead-action qualify

        # Set up CRM sequences (dry run first)
python src/main.py setup-sequences --dry-run

# Trigger niche sequential marketing
python src/main.py niche-sequential --channel sms --day 1

# Generate SOPs and playbooks
python src/main.py playbook --blueprint wholesale --market knoxville

### Common Flags

       |  | Flag | What It Does

         | --upload-datasift | Upload results to your DataSift CRM

         | --notify-slack | Send run summary to Slack/Discord

         | --skip-smarty | Skip address standardization

         | --skip-zillow | Skip Zillow enrichment

         | --skip-obituary | Skip deceased owner detection

         | --split | Separate CSV per county + notice type

         | -v | Verbose/debug logging

## Monthly Cost Breakdown

    What it costs to run SiftStack per month. Compare that to a $500-700 data manager doing the same work manually at 1/10th the volume.

      Minimum ($25/mo)
      Full Stack ($160/mo)

         |  | Service | Cost | Notes

           | Claude Pro | $20/mo | Will hit token limits fast during Claude Code use

           | 2Captcha | ~$3/mo | CAPTCHA solving

           | Smarty | Free | 250 lookups/month

           | OpenWeb Ninja | Free | 100 Zillow lookups/month

           | Serper.dev | Free | 2,500 Google searches

           | Total | ~$25/mo | + your DataSift subscription

      Best for: getting the pipeline running on a budget. Expect to hit Claude Pro token limits during heavy setup days.

         |  | Service | Cost | Notes

           | Claude Max | $100/mo | Recommended minimum for Claude Code at full power

           | 2Captcha | ~$3/mo | CAPTCHA solving

           | Anthropic API | ~$2/mo | Claude Haiku for LLM parsing

           | Tracerfy | ~$20/mo | Skip trace at $0.02/record

           | Trestle | ~$15/mo | Phone scoring at $0.015/phone

           | Ancestry.com | $29/mo | SSDI + obituary (optional)

           | Total | ~$160/mo | + your DataSift subscription

      Best for: serious operators running 1-2 counties daily with full enrichment. This is the tier I run personally.

    Start with the minimum tier. Add services one at a time as you see the value. The pipeline degrades gracefully. If you skip a service, SiftStack simply skips that enrichment step and moves on. Nothing breaks.

## Resources

    Everything you need to go deeper. Bookmark these links.

      [SiftStack GitHub Repository
Source code, documentation, and issue tracker](https://github.com/tyvhb/SiftStack)
      [VS Code Download
The code editor that powers your workspace](https://code.visualstudio.com/download)
      [Claude Code Documentation
Official docs for Claude Code features and usage](https://docs.anthropic.com/en/docs/claude-code)
      [Node.js Download
JavaScript runtime (LTS version)](https://nodejs.org)
      [Python Download
Python 3.12 (remember: check Add to PATH)](https://python.org/downloads)
      [Git Download
Version control and code download tool](https://git-scm.com/downloads)
      [2Captcha Dashboard
CAPTCHA solving service (~$3/mo)](https://2captcha.com)
      [DataSift Platform
Your CRM for lead management and marketing](https://datasift.ai)

        Challenge Hub
Back to the 5-Day Deal Flow Challenge

      Reset All Progress
