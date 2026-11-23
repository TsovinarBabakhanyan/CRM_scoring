# Medium post: CRM Scoring

Copy everything below the line into Medium's editor (medium.com → Write).
Lines starting with **[Image]** or **[Video]** are instructions, not text:
do what they say, then delete the line.

- **Title:** Your CRM Is Full of Leads. Here's How to Find the Ones Worth Calling.
- **Subtitle:** Why I built a lead scorer that shows its working — rules you can check, plus an AI note for what rules can't see
- **Tags (Medium allows 5):** Sales, Lead Generation, B2B, Artificial Intelligence, Startup
- **Cover image:** marketing/images/dashboard.png

---

# Your CRM Is Full of Leads. Here's How to Find the Ones Worth Calling.

## Why I built a lead scorer that shows its working — rules you can check, plus an AI note for what rules can't see

Open any sales team's CRM and you'll find the same thing: thousands of accounts, a few dozen of them actually worked last month, and nobody quite sure whether those were the right few dozen.

Finding leads is rarely the problem anymore. Lists are cheap. The hard part is knowing which accounts deserve your team's time *this week*.

CRM Scoring started with exactly that question — *which of these leads should we call first?* — and this post is about how I tried to answer it.

**[Image]** Upload marketing/images/dashboard.png here. Caption: *A CRM export, a minute after upload: every account scored and sorted Hot / Warm / Cold.*

## The problem with most lead scores

Most teams that score leads at all do it one of two ways.

**A spreadsheet of points.** +10 for the right industry, +5 for company size, and so on. It's transparent, but it only sees what's already in the CRM. It can't tell that a company just raised money or started hiring.

**A black-box AI score.** A number appears, maybe "87". Nobody knows why. Sales reps don't trust it, so they ignore it, and the score quietly dies.

I wanted both halves: a score you can check line by line, *and* something that notices the context a points table misses.

## How CRM Scoring works

You upload a CRM export (CSV or Excel). For every account, three things happen.

**1. Fill in the gaps.** Most CRM records are half empty. Each account is enriched with company-level data: industry, size, revenue, tech stack, location, and whether the company is hiring.

**2. Score it with rules you can see.** Each account is compared with your ideal customer profile on six criteria:

- Industry match
- Company size band
- Revenue band
- Tech stack match
- Location
- Hiring signal

Each criterion has a weight, and the breakdown is shown next to the score. If an account scores 62, you can see exactly where the 62 came from — and change the weights if they don't fit your business.

**3. Add an AI note for what rules can't see.** An AI model reads the account's profile and writes a short note: recent funding, a hiring surge, a competitor's tool already in their stack. That note feeds into the final score and sits next to it, in plain language.

The result is a ranked list: **Hot**, **Warm** or **Cold**, each with a reason.

## Three signs an account is worth a call this week

You don't need any tool to start using this thinking. Before your next pipeline review, check your top accounts for these three:

1. **They look like your best customers** on industry and company size. Your won deals are the best ideal customer profile you have.
2. **They're hiring.** New roles usually mean new budget and new problems to solve.
3. **They already use tools that work with yours.** An existing integration makes the buying decision smaller.

An account with all three is worth more of your team's time than ten that match none.

## What it deliberately doesn't do

Some decisions here were about what to leave out:

- **It scores companies, not people.** Nothing in the scoring judges an individual contact.
- **It doesn't write or send outreach.** It tells your team where to look. The conversation is theirs.
- **It doesn't change your CRM unless you click.** When an account is hot, one click sends it — score, bucket and reason — to Salesforce. A Slack alert can fire the moment an account turns hot.
- **Your data can stay with you.** CRM Scoring can be self-hosted on your own infrastructure, so your CRM export doesn't have to sit on someone else's servers.

## A few things that turned out to matter

**Language.** The app, the AI notes, the charts and the explanations all work in English, Russian and Armenian. Pick once and everything follows.

**Showing it to your manager.** The scoring overview turns into a ready PowerPoint deck in one click: the Hot / Warm / Cold mix, the score breakdown and the top 10 accounts.

**Agencies.** If you run outbound for several clients, each client gets their own workspace and their own ranked list.

**[Video]** Paste this link on its own line, then press Enter. Medium turns it into a video player if it can; if not, it stays a link:
https://www.tiktok.com/@tinatsovinarbabak/video/7711344409484250374

## Try it on your own data

Take your last 50 leads. How many match your best customers on industry, size and tech stack?

If you can't answer in under a minute, that's what CRM Scoring is for.

It's free to start, no card needed. Pro is $20 a month for teams scoring at volume, and Advanced is $40 a month for agencies with several clients.

👉 **[crmscoring.com](https://www.crmscoring.com)**

CRM Scoring is built in Armenia 🇦🇲 for sales teams everywhere. If you lead a sales team or an agency, I'd really like your honest feedback — leave a comment below, or reply after you've tried it.

*If this was useful, follow me here on Medium for more on lead scoring, sales operations and building a product from Yerevan.*
