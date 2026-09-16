# Funeral Contribution For Our Brother Emmanuel Papa Nii Quaye

A contribution ledger for the group. The product name is the group name set in the page settings; managers can change it at any time.

A single-page web app that records money contributions for a group (alumni
association, club, welfare fund, WhatsApp group). Everyone with the link can
see **who contributed and how much**. Only one or two designated managers can
change the record. Everyone else has read-only access, enforced by the host,
not by trust.

There are two builds of the same product in this folder:

- **`index.html`** is the claude.ai-hosted page. Live copy:
  https://claude.ai/artifact/8T97vnSBXb7ZEvZuGATJnz. Editing it needs a
  claude.ai account for each manager.
- **`webapp/`** is the standalone website with its own username and password
  sign-in. Managers need no account anywhere else. See `webapp/README.md`
  for the hosting guide. This is the recommended build when the managers
  are not the person who created the ledger.

The rest of this file describes the claude.ai-hosted page.

## What members see

- Group name, description, who the managers are, and when the ledger was last updated.
- Total collected, number of contributors, number of payments, and progress towards a goal if one is set.
- **By member** view: each person once, with how many payments they made, when they last paid, and their total.
- **All entries** view: every payment in date order with an optional note.
- A name search box and a CSV export.

Members cannot edit anything. The manager tools never appear for them, and
even if someone tampered with the page in their browser, the host rejects a
save from anyone who is not an editor.

## What managers can do

A manager sees a **Manager tools** button. From there they can:

- Record a contribution (name, amount, date received, note).
- Edit or delete an existing entry from the **All entries** view.
- Change the group name, description, currency code, fund goal, and the manager names shown on the page.
- Clear every entry (two presses, then Publish) if the ledger must be reset.

Changes are staged first and shown with an "unsaved" tag. Nothing reaches the
members until the manager presses **Publish** in the bar at the bottom. That
saves a new version of the page for everyone. **Discard** throws the staged
changes away.

## How access control works

The page is an Artifact hosted on claude.ai. Two host features do the work:

1. **Sharing.** The owner shares the page by link. Anyone with the link can view it.
2. **Editors.** The owner grants edit access to at most one or two trusted
   people from the page's share menu. The page saves itself with the
   *viewer's* authority, so a save from anyone else is refused with a
   read-only notice.

There are no passwords in the page and nothing to leak. The list of manager
names shown on the page is informational only. Real edit rights come from the
share settings.

## Setting it up for your group

1. Open the live page. As the owner you already have the manager tools.
2. Press **Manager tools** and check **Group settings**: the name, the
   currency (a three-letter code such as GHS, USD, GBP, NGN, KES, ZAR), an
   optional goal, and the manager names. Press **Stage settings**, then
   **Publish**.
3. Record the first contributions with the form, then **Publish**.
4. Use the share menu on the page to get a link and to add your second
   manager as an editor.
5. Post the link in the WhatsApp group. Members tap it and see the ledger.

## Recording contributions

Each time money comes in, a manager opens the link, presses **Manager tools**,
fills in the form, and presses **Publish**. The whole group sees the update
the next time they open the link.

## Files

- `index.html` is the entire app: styles, markup, data, and script in one
  file. It ships with an empty ledger under the group's name. The current ledger data lives in the `<script id="state">` block and
  is rewritten by the page itself on every publish.
- `tests/verify.js` is a Playwright script that exercises the read-only
  view, the manager flow, the CSV export, and a republish round trip.

Run the check with:

```
node tests/verify.js /tmp/ledger-check
```

It needs Node and a global Playwright install with Chromium.

## Limits

- The ledger is stored inside the page, so it suits a few thousand entries at most.
- Editors need a claude.ai account to be granted edit rights. Viewers do not need one if the page is shared by public link.
- Two managers editing at the same moment: the second publish is refused as a
  conflict, the page reloads, and the second manager is offered their staged
  changes again to re-apply.
