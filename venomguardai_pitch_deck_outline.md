# VenomGuard AI: Pitch Deck and Product Blueprint

> This document is both a presentation outline and an implementation brief. An AI reading it should be able to understand the product purpose, users, routes, state transitions, data contracts, business rules, and visual interface well enough to recreate the experience without guessing.

## 1. Product Identity

**Product:** VenomGuard AI  
**Category:** Community snakebite reporting, triage, education, and referral coordination  
**Current implementation:** Django web application with server-rendered templates, session-based access control, SQLite development storage, Django REST Framework APIs, and a mobile-first interface.

**One-line description:** VenomGuard AI helps communities recognize and report suspected snakebite incidents, receive immediate safety guidance, and connect frontline healthcare workers to high-risk cases and nearby care facilities.

**Core promise:** Make the next correct action obvious during a frightening, time-sensitive snakebite event.

**Important product boundary:** This is a decision-support and coordination tool, not a replacement for clinical judgment, emergency services, antivenom protocols, or a full electronic medical record.

## 2. Pitch Deck Narrative

### 2.1 Title Slide

- VenomGuard AI
- Faster snakebite recognition, safer first aid, and stronger referral pathways
- Community reporting and healthcare coordination in one mobile-first experience

### 2.2 The Problem

Snakebite envenomation is a time-sensitive public health problem, especially where transport, antivenom, trained staff, and reliable information are unevenly distributed. People may not know what first aid is safe, may delay seeking care, or may not know where stocked treatment is available. Community observations and clinical response are often disconnected.

The result is avoidable delay between:

1. Seeing or experiencing a suspected bite.
2. Understanding the level of risk.
3. Taking safe immediate action.
4. Finding an appropriate health facility.
5. Sending and tracking the referral.

### 2.3 Why This Matters

- A suspected bite can deteriorate before a person reaches care.
- Harmful traditional interventions can increase injury or delay treatment.
- Frontline workers need a fast operational view of active and high-risk cases.
- Facilities need better referral information and visibility into antivenom availability.
- Public health teams need structured, location-aware data rather than disconnected reports.

### 2.4 Solution

VenomGuard AI joins four connected capabilities:

- **Community reporting:** A familiar timeline where users submit a sighting or incident with a photo, description, bite status, time, and location.
- **Risk assessment:** A symptom-based assessment that returns risk, likely venom category, possible snake information, severity, and recommended next actions.
- **Immediate education:** First aid, prevention, snake knowledge, job aids, and facility guidance presented in short, mobile-readable modules.
- **Healthcare operations:** CHW dashboard, case review, risk alerts, facility selection, referral submission, and status tracking.

### 2.5 Value Proposition

For community members:

- Know what to do immediately.
- Avoid dangerous or delaying actions.
- Find nearby help faster.
- Report an incident with useful evidence and context.

For CHWs and healthcare staff:

- See active and high-risk cases in one place.
- Review patient, symptoms, location, photo, risk, and status.
- Refer to an appropriate facility with a structured note.
- Coordinate care with less manual searching.

For health programs:

- Capture structured, location-aware case and sighting data.
- Monitor risk, referrals, and outcomes.
- Build a foundation for regional planning and service expansion.

## 3. Users and Permissions

### 3.1 Community Member

The community member needs quick, plain-language guidance. They can:

- Enter the protected app.
- Select nationality/country and member type.
- View a country-aware community timeline.
- Switch to broader global activity where supported.
- Submit a snake sighting or suspected bite report.
- Run a symptom-based bite assessment.
- Open the First Aid Guide.
- Learn about snakes and prevention.
- Find nearby help and antivenom-capable facilities.
- View profile/settings information.

### 3.2 Healthcare Worker / CHW

The CHW needs a compact operational workspace. They can:

- Enter the healthcare flow through the same protected access gate.
- View the dashboard and case metrics.
- Filter cases by all, open, high risk, and resolved.
- Open a full case detail record.
- Review photo, symptoms, clinical notes, risk, and history.
- Send a referral to a selected facility.
- Choose whether patient details are shared.
- Call the receiving facility.
- Submit a report from the healthcare navigation bar.
- Access settings and healthcare navigation.

### 3.3 Future Program Administrator

Not a fully implemented role yet. A future administrator may manage facility stock, educational content, clinical rules, users, audit history, and regional analytics.

## 4. Access, Session, and Context Logic

### 4.1 Protected Entry

Protected pages require the custom session gate. The current prototype does not rely on full user authentication for ordinary app access.

1. User opens `/venomguard/access/`.
2. User enters the configured app password.
3. User selects nationality/country.
4. User selects member type.
5. The selection is stored in the session.
6. Community users go to the community home.
7. Healthcare users go to the CHW dashboard.
8. Protected routes redirect back to access if the access flag is missing.

The current development password is `Dr.EricNyarko`; it must be treated as configuration and replaced with a secure secret in production.

### 4.2 Session Keys and Defaults

- Access flag: `snakebite_access_granted`
- Country/nationality: `snakebite_nationality`
- Member type: `snakebite_member_type`
- Supported member types include `community` and `healthcare`.
- If member type is absent, the resolver falls back to the authenticated profile when available, then to `community`.
- The selected country is the source of truth for user context and default report coordinates.
- A report also stores its member type in the database on both the submitted `SnakeSighting` and generated `PatientCase`.

### 4.3 Context Rules

- Country labels shown to users must not rely only on stale session location.
- When coordinates are available, geographic bounds are used to determine the real country label for records.
- If browser geolocation is unavailable or denied, the selected country’s default coordinates are used.
- Last-known browser coordinates may be stored locally for convenience, but stale coordinates must not silently override the active country context.
- A user’s country and member type should be visible through the shared profile/context treatment where the screen supports it.

## 5. Canonical Route Map

All routes below use the active `/venomguard/` prefix in the current project.

### 5.1 Entry and Navigation

| Route | Purpose | Primary audience |
|---|---|---|
| `/venomguard/access/` | Password, country, and member-type entry | Everyone |
| `/venomguard/` | Role-aware home redirect | Everyone |
| `/venomguard/community-home/` | Community timeline and actions | Community |
| `/venomguard/chw-dashboard/` | CHW operational dashboard | Healthcare |
| `/venomguard/settings/` | Profile and context settings | Everyone |

### 5.2 Community Routes

| Route | Purpose |
|---|---|
| `/venomguard/report/` | Submit a snake sighting or suspected bite |
| `/venomguard/community-bite-assessment/` | Select symptoms and calculate risk |
| `/venomguard/community-risk-result/` | View assessment result and recommended actions |
| `/venomguard/community-nearest-help/` | Find nearby care and antivenom facilities |
| `/venomguard/first-aid/` | Read immediate snakebite first aid |
| `/venomguard/education-training/` | Learn hub for first aid, prevention, resources, and videos |
| `/venomguard/snakes-in-my-area/` | Browse regional snake information |
| `/venomguard/resources/` | Browse educational resources and job aids |
| `/venomguard/antivenom-stock-map/` | View facility and stock map |

### 5.3 Healthcare Routes

| Route | Purpose |
|---|---|
| `/venomguard/case-details/<id>/` | Review a complete case |
| `/venomguard/case/<id>/send-referral/` | Select facility and send referral |
| `/venomguard/dashboard/<metric>/` | Filtered operational list, such as `risk_alerts` |
| `/venomguard/report/` | Submit a report from healthcare flow |

### 5.4 APIs

- `/venomguard/api/snakes/`
- `/venomguard/api/health-facilities/`
- `/venomguard/api/first-aid-steps/`
- `/venomguard/api/educational-materials/`
- `/venomguard/api/assessments/`
- `/venomguard/api/nearby-antivenom-facilities/`
- `/venomguard/api/bootstrap/`
- `/venomguard/api/sightings/`
- `/venomguard/api/sighting/<id>/`

## 6. Shared UI System

The app should feel like one product even though different screens serve different roles.

### 6.1 Visual Direction

- Mobile-first, compact, operational, and readable under stress.
- Dark charcoal foundation rather than a separate light-green theme per screen.
- Gold is the primary action and active-navigation color.
- Red is reserved for danger, urgent risk, and emergency attention.
- Green communicates availability, stability, or successful status.
- Muted gray-blue text supports metadata without competing with actions.
- Panels are dark, bordered, and lightly elevated; avoid nested decorative cards.
- Rounded corners are restrained, generally 12 to 18px.
- Use a constrained content width around 480px for the mobile experience, while allowing the shell to sit naturally on larger screens.

### 6.2 Global Shell

Every major app screen should use the shared `snakebite/base.html` shell:

1. Sticky top bar with VenomGuardAI brand mark and member-type pill.
2. Centered page shell with consistent horizontal padding.
3. Content sections using shared variables such as `--bg`, `--panel`, `--card`, `--line`, `--text`, `--muted`, `--gold`, `--red`, and `--green`.
4. Fixed bottom navigation appropriate to the active role.
5. Bottom padding large enough that fixed navigation never hides content.

### 6.3 Buttons and States

- Primary action: gold gradient, dark text, strong weight.
- Secondary action: transparent or low-contrast dark panel with a border.
- Danger action: red-tinted panel and red text.
- Buttons have stable minimum heights and do not resize when text changes.
- Submit actions must disable after the first valid click.
- Loading actions show a spinner and a clear state label such as `Submitting report...`.
- Empty media uses a visible placeholder rather than a broken image frame.
- Error states explain what must be corrected without erasing valid user input.

### 6.4 Navigation

Community navigation has five items:

1. Home
2. Learn
3. Report
4. Alerts
5. Profile

Healthcare navigation has five items:

1. Home
2. Cases
3. Alerts
4. Report
5. More

The navigation uses equal-width grid columns, stable icon/label heights, an active gold treatment, and labels that do not wrap on ordinary mobile widths.

### 6.5 Responsive Rules

- Cards and forms must fit within narrow mobile screens without horizontal scrolling.
- Long patient names, facility names, and labels use safe wrapping or ellipsis.
- CTA groups stack or wrap when required.
- Fixed navigation must account for safe-area insets.
- Image containers have stable dimensions.
- A loading state must not cause layout shift.

## 7. Screen-by-Screen UI Specification

### 7.1 Access Screen

Purpose: establish access and context.

UI elements:

- VenomGuard branding.
- Password field and validation message.
- Country/nationality options with clear selection state.
- Member-type options for Community and Healthcare.
- Continue/enter action.
- Contextual feedback when required fields are missing.

Behavior:

- Do not expose protected content before password validation.
- Preserve valid selections after validation errors.
- Redirect based on member type after successful entry.

### 7.2 Community Home / Timeline

Purpose: provide situational awareness and quick actions.

UI elements:

- Timeline header and selected-country context.
- Community alerts/activity feed.
- Primary `Start Bite Assessment` action.
- Supporting actions beside it: `First Aid Guide` and `Find Nearest Help`.
- Country selector before a country is selected.
- Sighting cards with image, placeholder, headline, species/location, time, and risk.
- Detail modal or detail interaction for a selected sighting.
- Community bottom navigation.

Behavior:

- Feed can be filtered by nearby country context or global activity.
- Missing or broken images become a `No image` placeholder.
- Assessment remains a distinct action from the Learn hub.

### 7.3 Report Sighting

Purpose: capture a structured community or healthcare report.

Fields:

- Photo, selected via camera or gallery.
- Suspected species.
- Headline.
- Description.
- Was anyone bitten: Yes/No.
- WhatsApp/phone, optional.
- Time seen.
- Hidden latitude and longitude populated by geolocation/default country coordinates.

Submission logic:

1. Validate headline, description, and required photo.
2. Resolve current country and member type from session/profile context.
3. Get browser coordinates when possible.
4. Fall back to selected-country coordinates when necessary.
5. Create a `SnakeSighting` record.
6. Create a linked operational `PatientCase` record.
7. Store the same `member_type` on both records.
8. Set case risk to High when the user reports a bite, otherwise Medium.
9. Set the new case status to Open.
10. Redirect to the case details page.

Loading behavior:

- On first submit, disable the button.
- Show a spinner.
- Change label to `Submitting report...`.
- Keep the state active while geolocation is being resolved and the multipart request is submitted.
- Block duplicate submissions.

### 7.4 Bite Assessment

Purpose: let a community member evaluate symptoms and understand urgency.

UI elements:

- Symptom checklist grouped by understandable body system or symptom category.
- Clear selected/unselected states.
- Continue or calculate action.
- Plain-language risk result.

Output:

- Severity score.
- Low, Medium, or High risk.
- Likely venom category: Neurotoxic, Hemotoxic, or Uncertain.
- Possible snake or envenomation type.
- Recommended action.
- First aid and nearest-help links.

### 7.5 Risk Result

Purpose: convert assessment output into a next action.

The highest-priority content should appear first:

1. Risk severity.
2. Immediate recommended action.
3. Emergency or referral call to action.
4. First aid guidance.
5. Supporting explanation and likely venom information.

High-risk results should clearly advise urgent referral and should never bury the emergency action below educational content.

### 7.6 First Aid Guide

Purpose: provide immediate, safe, short-form instructions.

UI elements:

- Emergency-care heading.
- Back link to community home.
- Emergency warning panel.
- Call emergency services action, currently `112` in the prototype.
- Numbered steps.
- Explicit “do not” guidance.
- Shared global shell and community navigation.

Content principles:

- Keep the person calm.
- Immobilize the affected limb.
- Remove tight items.
- Do not cut, suck, burn, or apply harmful substances.
- Arrange rapid transport to a health facility.
- Do not delay transport while trying to identify or catch the snake.

### 7.7 Learn / Education and Training

Purpose: make prevention and response knowledge discoverable.

The Learn navigation item opens the education hub, not the bite assessment.

UI elements:

- `Learn about snakebite` heading.
- Knowledge-centre introduction.
- Learning-path prompt that directs users to First Aid first when appropriate.
- Module cards for:
  - First Aid for Snakebite.
  - Snake Biology and Prevention.
  - Posters and Job Aids.
  - Training Videos and Demonstrations.
  - Find Care Near You.
- Each card includes a title, useful description, icon, and route arrow.
- Shared global shell and active Learn navigation.

### 7.8 CHW Dashboard

Purpose: provide a concise operational overview.

UI elements:

- Healthcare dashboard header and Live status.
- New Snakebite Case action.
- Metric cards for My Cases, Alerts, High Risk, and Referrals.
- Filter controls: All Cases, Open, High Risk, Resolved.
- Case cards containing photo or placeholder, patient, location, case ID, risk, status, and timestamp.
- Recent Alerts section.
- Healthcare bottom navigation: Home, Cases, Alerts, Report, More.

Behavior:

- Case cards link to case details.
- Broken photos become the same visible no-image placeholder used by the community flow.
- Filter controls update the visible case cards without losing their stable layout.
- `New Alerts` means high-risk cases still marked Open.
- The `Risk Alerts` metric page includes all high-risk cases, including resolved records.

### 7.9 Risk Alerts List

Purpose: show cases requiring high-risk awareness or review.

Definition:

- A risk alert is a `PatientCase` with `risk_level = high`.
- The `/dashboard/risk_alerts/` list includes every high-risk case.
- The dashboard’s `New Alerts` count is narrower: high-risk and `status = open`.

Each list item should show:

- Case ID.
- Patient name.
- Location.
- Created date.
- Current status.
- Link to full case details.

### 7.10 Case Details

Purpose: give a CHW enough information to decide the next action.

UI sections:

- Case Details header with active-case status.
- Case ID, patient, age/sex, location, and created time.
- Case photo or `No image available` placeholder.
- Risk level and current case status.
- Suspected snake.
- Assessment date.
- Symptoms.
- Clinical notes and patient metadata.
- Recent assessments.
- Referral history.
- Fixed or clearly available actions: `Send Referral` and `Call Facility`.

Design requirement: clinical facts and urgent actions must be easier to scan than historical detail.

### 7.11 Send Referral

Purpose: coordinate transfer from a case to a receiving facility.

UI elements:

- Care-coordination header and back link.
- Case banner with case ID, patient, location, and risk.
- Suggested facility panel.
- Distance, facility type, antivenom availability, and open/call-ahead status.
- Receiving-facility selector.
- Referral note textarea.
- Share patient details selector.
- `Send Referral` primary action.
- `Cancel` secondary action.
- Healthcare bottom navigation.

Submission behavior:

1. Select requested facility, or fall back to a suggested/available facility.
2. Save or update a `Referral` record.
3. Store notes and patient-detail sharing choice.
4. Move the case to `In Transit` when referral is sent.
5. Return the user to an appropriate operational view.

### 7.12 Nearest Help and Stock Map

Purpose: make care availability actionable.

Display:

- Facility name and type.
- Region and coordinates.
- Distance from selected/user coordinates.
- Antivenom availability.
- Stock update time where available.
- Cost where available.
- Contact number.
- Call or referral action.

The nearest facility calculation should be based on coordinates and should distinguish antivenom-capable facilities from general facilities.

## 8. Risk and Clinical Decision Logic

### 8.1 Symptom Assessment Engine

The risk engine normalizes symptom text and applies symptom weights and venom markers.

Important markers:

- Neurotoxic: drooping eyelids/ptosis, muscle weakness, respiratory distress, and related neurological signs.
- Hemotoxic: bleeding gums, dark urine, bruising, systemic swelling, abnormal bleeding, and related blood/tissue signs.

Example classification:

- Neurotoxic signs alone: High Risk, likely Neurotoxic.
- Hemotoxic signs alone: High Risk, likely Hemotoxic.
- Both categories: High Risk, likely Uncertain.
- Severity score at least 40: High Risk.
- Severity score at least 20: Medium Risk.
- Otherwise: Low Risk.

The thresholds and marker lists are clinical product rules. They require validation with qualified clinical stakeholders before production use.

### 8.2 PatientAssessment Scoring

`PatientAssessment` derives a severity score from symptom count and predicted envenomation:

- Each symptom contributes 10 points.
- A predicted envenomation adds 15 points.
- Score at least 40 becomes High.
- Score at least 20 becomes Medium.
- Lower scores become Low.

The score and risk level are synchronized after symptom changes.

### 8.3 PatientCase Alert Logic

`PatientCase` has:

- `risk_level`: Low, Medium, High.
- `status`: Open, In Transit, Resolved.

The current report flow sets:

- Bite reported: High.
- No bite reported: Medium.
- New case status: Open.

New cases currently default to High at the model level, so all creation paths should set risk explicitly when the source logic knows the risk.

## 9. Referral and Case State Machine

### Case states

- **Open:** Requires monitoring, triage, or action.
- **In Transit:** Referral has been sent and transfer is underway.
- **Resolved:** Case has reached a completed state.

### Referral states

- **Pending:** Referral initiated but not fully sent.
- **Sent:** Referral sent to the destination facility.
- **Acknowledged:** Receiving facility has acknowledged it.

### Typical transition

`Report submitted -> Case Open -> CHW reviews -> Referral Sent -> Case In Transit -> Case Resolved`

Every transition should preserve timestamps and make the current state obvious in the UI.

## 10. Data Model and Persistence Contract

### 10.1 Region

- `name`
- `code`

### 10.2 HealthFacility

- `name`
- `facility_type`: district hospital, health center, or CHPS
- `region`
- `latitude`
- `longitude`
- `contact_number`
- `antivenom_available`
- `antivenom_cost`
- `last_stock_update`

### 10.3 Snake

- `common_name`
- `scientific_name`
- `venom_type`: hemotoxic, neurotoxic, or cytotoxic
- `region_distribution`
- `description`
- `visual_features`
- `image`

### 10.4 Symptom

- `name`
- `slug`
- `description`
- `body_system`

### 10.5 EnvenomationType

- `type_name`
- `target_snakes`
- `associated_symptoms`

### 10.6 PatientAssessment

- `region`
- `patient_age_group`
- `symptoms_present`
- `severity_score`
- `predicted_envenomation`
- `risk_level`
- `recommended_action`
- `timestamp`

### 10.7 FirstAidStep

- `step_number`
- `title`
- `description`
- `do_statement`
- `dont_statement`
- `icon_name`
- `target_audience`

### 10.8 EducationalMaterial

- `title`
- `category`
- `file_attachment`
- `video_url`
- `payload_body`
- `downloaded_count`

### 10.9 SnakeSighting

- `photo`
- `headline`
- `description`
- `was_bitten`
- `member_type`
- `contact_number`
- `time_seen`
- `latitude`
- `longitude`
- `created_at`
- `suspected_species`

`member_type` records whether the report came from a community member or healthcare worker. Existing rows default to `community` through the database migration.

### 10.10 PatientCase

- `case_id`
- `patient_name`
- `patient_age`
- `gender`
- `location`
- `symptoms`
- `suspected_snake_type`
- `risk_level`
- `status`
- `clinical_notes`
- `photo`
- `member_type`
- `assigned_to`
- `is_active`
- `created_at`
- `updated_at`

### 10.11 Referral

- `case`
- `destination_facility`
- `notes`
- `shared_patient_details`
- `status`
- `sent_at`

## 11. Report-to-Case Data Contract

A report is intentionally represented twice:

1. `SnakeSighting` preserves the community-facing observation.
2. `PatientCase` creates an operational record for healthcare follow-up.

Shared values should include:

- Photo.
- Description-derived symptoms.
- Species or suspected snake type.
- Country-derived location.
- Member type.

The two records serve different workflows and should not be collapsed into one model without a deliberate migration and workflow review.

## 12. API and Integration Contract

The REST API supports future mobile clients, synchronization, and integrations.

Expected capabilities:

- Retrieve snakes and regional information.
- Retrieve health facilities and stock state.
- Retrieve first aid and educational material.
- Create symptom assessments.
- Calculate nearby antivenom facilities.
- Bootstrap reference data for offline or mobile clients.
- Retrieve sightings and sighting detail.

API responses should use stable identifiers, explicit risk/status values, ISO timestamps, nullable photo URLs, and predictable empty collections. Clients must handle missing media and unavailable geolocation gracefully.

## 13. Empty, Error, and Loading States

Every important workflow needs a deliberate state.

### Empty states

- No sightings: explain that no reports are available yet.
- No case matches a filter: show a concise operational message.
- No referral history: say that no referral has been recorded.
- No facility: show a clear fallback and a call-ahead instruction.
- No image: show a designed placeholder, never a blank or broken frame.

### Validation errors

- Show errors near the relevant field or in a visible alert region.
- Preserve all valid text and selections.
- Explain photo requirements and description requirements.
- Never create a partial case when required report data is invalid.

### Loading states

- Report submission: spinner, `Submitting report...`, disabled button.
- Location resolution: keep the same submit state; do not invite duplicate clicks.
- API timeline loads: show a stable skeleton or loading label without shifting card dimensions.
- Facility lookup: communicate searching and no-result states.

## 14. Security, Privacy, and Safety

Current prototype controls:

- Protected views use the session gate.
- Forms use CSRF protection.
- User-selected context is stored in the session.
- Referral flow explicitly asks whether patient details should be shared.

Production requirements:

- Replace the shared prototype password with real authentication and role-based authorization.
- Protect patient data with least-privilege access, audit logs, encryption, and retention rules.
- Validate uploaded file type, size, content, and storage location.
- Avoid exposing sensitive patient data in URLs, logs, or unrestricted APIs.
- Validate all clinical content with qualified professionals.
- Add consent and privacy language appropriate to each deployment country.
- Treat emergency messaging as safety-critical content subject to clinical governance.

## 15. Seed Data and Demonstration Behavior

The project includes a seed command for regions, snakes, facilities, first-aid steps, educational resources, cases, and referrals.

Demo data should make it possible to demonstrate:

- Low, medium, and high risk.
- Open, in-transit, and resolved cases.
- Available and unavailable antivenom.
- Community and healthcare reports.
- Missing and valid images.
- Multiple countries and coordinate-based filtering.
- Referral history and suggested facilities.

## 16. Quality and Validation Strategy

### Automated tests

Cover at minimum:

- Access protection and role redirects.
- Country and member-type persistence.
- Report validation and report-to-case creation.
- `member_type` copied to both persisted report records.
- Default coordinates and geolocation fallback.
- Country and global feed filtering.
- Risk engine thresholds and marker combinations.
- Dashboard metric counts and filter results.
- Broken/missing image fallback behavior.
- Case detail and referral transitions.
- Named navigation routes and active states.
- Loading-state DOM behavior where practical.

### Manual checks

- Test a narrow mobile viewport and a wider desktop viewport.
- Verify fixed bottom navigation does not cover buttons or form fields.
- Verify long names and facility labels do not overflow.
- Verify a broken image URL produces a visible placeholder.
- Verify report submission cannot be double-clicked.
- Verify the correct role’s navigation appears on each protected flow.
- Verify emergency actions are visible before secondary content.

## 17. Current Implementation Status

Implemented or recently aligned:

- Session-gated community and healthcare flows.
- Country-aware reporting and timeline behavior.
- Community assessment, first aid, nearest-help, and education routes.
- Shared community and healthcare navigation.
- Learn navigation connected to the Education and Training hub.
- First Aid page aligned with the shared app shell.
- Education page aligned with the shared app shell.
- Case details page aligned with the shared dark/gold theme.
- Send Referral page aligned with the shared healthcare theme.
- CHW healthcare bottom navigation with Home, Cases, Alerts, Report, and More.
- Missing/broken image placeholders in community, dashboard, and case-detail flows.
- Report member type persisted on `SnakeSighting` and `PatientCase`.
- Report submission loading and duplicate-click prevention.

Known prototype limitations:

- Access is not production-grade authentication.
- Clinical risk rules need formal clinical validation.
- Facility and antivenom data may be seeded/demo data.
- Some educational module destinations are placeholders or need richer content.
- Automated Django tests may require a supported Django/Python version combination in the development environment.

## 18. Roadmap

### Near term

- Add real user authentication and role-based permissions.
- Validate risk rules with clinicians and snakebite specialists.
- Improve facility freshness, stock timestamps, and contact accuracy.
- Add richer education content and real training media.
- Add automated tests for report persistence and loading state.
- Improve accessibility, including semantic icons, focus states, contrast, and screen-reader labels.

### Medium term

- Add multilingual content.
- Add offline-first or installable mobile support.
- Add push/SMS/WhatsApp referral notifications.
- Add CHW assignment and referral acknowledgement workflows.
- Add regional analytics and program dashboards.
- Integrate with ministries, NGOs, hospitals, and emergency transport networks.

### Long term

- Predictive geographic risk mapping.
- Facility capacity and live stock synchronization.
- Clinical decision-support integrations.
- Federated country deployments with local data governance.
- Research dashboards for prevention and outcome improvement.

## 19. Suggested Demo Script

1. Open the access screen.
2. Enter the prototype password.
3. Select a country and Community.
4. Show the community timeline and country context.
5. Open Learn and show the education hub.
6. Open First Aid and demonstrate the emergency panel.
7. Return to the community home and start a bite assessment.
8. Show a high-risk result and nearest-help action.
9. Open Report, select a photo, and submit while showing the loading state.
10. Follow the generated case into the healthcare flow.
11. Switch to Healthcare through the access context.
12. Show CHW dashboard metrics, filters, report navigation, and image fallback.
13. Open a high-risk case.
14. Review clinical details and referral history.
15. Send a referral to the suggested antivenom facility.
16. Explain the case transition from Open to In Transit.

## 20. Closing Statement

VenomGuard AI turns a fragmented snakebite response into a connected sequence: recognize, report, assess, act, locate care, refer, and monitor. Its strength is not a single screen or algorithm. It is the connection between a community member’s urgent moment and a healthcare worker’s next operational decision.

**Closing line:** Saving lives through faster snakebite response, clearer guidance, and stronger referral pathways.

## 21. Final Call to Action

VenomGuard AI is ready for focused clinical validation, community usability testing, facility-data partnerships, and a controlled pilot with frontline health workers. The next investment should improve trust, clinical safety, data quality, and response speed in the places where snakebite care is hardest to reach.
