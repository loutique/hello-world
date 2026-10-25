# Costume voting module

This is an internal module of the existing Django application, not an online voting system. Public registration routes, models and submissions are unchanged. Render configuration is unchanged.

## Access and language

The entry point is `/admin/costume-voting/`. Existing active staff authentication is required on **every** endpoint, including images, saves, reports and history. Assign the `registrations.operate_costume_voting` permission to operators; superusers already have it. Only authorized staff see the navigation link. Creation and all competition screens use Ukrainian. The surrounding registration administration retains Russian. No participant accounts or external API credentials are needed.

## Architecture and persistence

`CostumeVotingSession` is a versioned JSON aggregate containing jury members, contestants, shortlist, paper-ballot totals and the jury matrix. This keeps a competition's related state atomic without a second database or partial multi-table saves. The server validates its explicit schema on every write. IDs are UUIDs; jury identifiers survive name edits. Original registration numbers are separate from final numbers. `CostumeVotingPhoto` stores stripped, resized JPEG pixels in PostgreSQL; it never relies on Render's temporary filesystem. `CostumeVotingAudit` stores versioned state and result snapshots with actor and timestamp. Audit snapshots contain private data and are not public reports.

Migration `0012` adds these three tables and the operator permission. It does not modify existing registration records. Run the normal requirements installation and `python manage.py migrate`; the existing container startup already applies migrations. ReportLab and packaged, licensed DejaVu fonts provide Ukrainian PDF output without operating-system font installation or external document services.

All writes use a transaction, row lock and expected revision. A stale tab receives HTTP 409, not a silent overwrite. Draft edits autosave after 650 ms. Next validates and persists before returning the next route. The interface reports failed saves and warns before leaving an unsaved page. Nothing can guarantee persistence during a network outage before a successful server response; the UI never reports such an edit as saved. Explicit Save allows a retry. After a connection error, keep the tab open until saving succeeds. On a version conflict, preserve local input before refreshing; automatic merging is deliberately avoided.

Jury entry locks earlier competition stages on the server. Locked stages remain viewable. Disqualification and its reason can still be entered; all vote totals and awards remain stored. Changed scoring data invalidates the result snapshot, and presenter/PDF access requires recalculation. Completion freezes further edits. Sessions are independent, so create separate rehearsal sessions.

Practical request-size limits are 2,000 contestant rows and 200 jury rows: the browser uses one editable jury matrix. Uploads are limited to 5 MB and 25 megapixels before processing. JPEG, PNG and WebP are supported; camera capture depends on the device. HEIC must be converted by the device or user. Photos are bounded to 1,000 pixels per side, converted to JPEG and stripped of EXIF metadata.

## Seven steps

1. Name the active jury members; add members or deactivate unused rows.
2. Enter contestant numbers and names. Ten empty rows appear initially. Photos, Instagram and phone are optional and can be changed before jury entry.
3. Explicitly choose all contestants or a manual shortlist. A shortlist must contain exactly its requested count; no score-based automatic selection exists. Finalists receive sequential final numbers; others remain in storage.
4. Enter box total, invalid ballots and votes per finalist, including later-disqualified finalists. Totals must reconcile before starting jury entry.
5. Use one matrix. Every active jury column must contain exactly one 5, one 3 and one 1; all remaining cells are 0. Disqualified contestants retain their original awards without forced redistribution.
6. Review audience, jury and combined calculations, warnings and audit details. Recalculate after a disqualification. Supply disqualification reasons before public PDF export.
7. Read the deterministic Ukrainian presenter script and download the public PDF. Complete the session when changes should be frozen.

There must be at least three eligible finalists when jury entry begins. A bank with zero eligible votes or awards cannot be proportionally distributed, so calculation is blocked with an explanation. Complete equality after all specified ranking criteria produces a shared place; no random winner is invented. A shortlist must retain at least three contestants to allow the 5/3/1 rule.

## Mathematics and presentation

All scoring and ranking use `fractions.Fraction`, not binary floating point. Each eligible audience vote contributes to a 750-point bank; each eligible jury point contributes to a 250-point bank. Disqualified votes are excluded from calculation bases, not reclassified as invalid ballots. Exact numerator/denominator and decimal representations are persisted separately from public integer scores.

Largest remainder allocation conserves each integer bank. Equal audience remainders use higher audience vote count; equal jury remainders use more 5s, then 3s, then 1s. If all meaningful allocation criteria remain equal, original registration order is a deterministic final fallback, disclosed in report methodology and at a material allocation boundary. This fallback does not determine competition places.

Final ranking uses exact combined score, then audience result, audience votes, jury 5s, 3s and 1s. Ranking ties and applied criteria are flagged. A full remaining tie shares a place. Public integer totals may appear tied or differ from exact-score ordering; exact scores decide places.

The presenter uses templates only, with the approved introduction unchanged. Its audience queue is frozen to reverse jury order for that calculation; adding audience points never reorders the queue. It evaluates exact interim standings, remaining audience points, leadership, top-three changes, major jumps, the last three results and jury/audience disagreement. Stage notes are separate from spoken copy. Every revealed result includes jury, audience and combined announced points. A new calculation after operator changes regenerates the script; do not change a competition during an announcement.

The private PDF-download endpoint produces a publishable Ukrainian document from an explicit contact-free result snapshot. It includes methodology, totals, excluded votes, individual calculations and fractions, complete jury matrix, status/reasons, final breakdown and material tie information. Jury tables split horizontally into groups of six columns for readability. Participant photos and contact details are never passed to the renderer. Download and publish the report yourself; there is no public route to organizer data.

## Validation

`registrations.test_voting` covers schema validation, exact conservation, randomized audience distributions, disqualifications, missing/duplicate jury awards, manual shortlists, reconciliation, ties, presenter order, access control, CSRF, stale revisions, atomic transitions, invalidation/completion, photo isolation and PDF export. Run it with the existing registration suite: `python manage.py test`.
