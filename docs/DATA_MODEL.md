# Data Model

The MVP uses Google Sheets via a Repository Pattern. 
The spreadsheet will contain multiple tabs (sheets). Below is the exact mapping of entities to sheet tabs and their required fields.

## Google Sheets Tab Mapping
- Tab 1: `Companies`
- Tab 2: `Contacts`
- Tab 3: `Deals`
- Tab 4: `Activities`
- Tab 5: `Tasks`
- Tab 6: `ResearchSources`
- Tab 7: `AIRecommendations`
- Tab 8: `AuditLogs`

## Entities

### 1. Company (Tab: Companies)
- `id` (UUID)
- `name_en`
- `name_ar`
- `domain` (Normalized, Unique)
- `sector`
- `city`
- `description`
- `products`
- `digital_footprint`
- `compliance_status`
- `fit_score`
- `confidence_score`
- `created_at`
- `updated_at`
- `archived_at`
- `verification_status`

### 2. Contact (Tab: Contacts)
- `id` (UUID)
- `company_id` (FK)
- `name`
- `title`
- `email`
- `phone`
- `relationship_level`
- `source_url`
- `verification_status`
- `notes`

### 3. Deal (Tab: Deals)
- `id` (UUID)
- `company_id` (FK)
- `service_requested`
- `assigned_department`
- `suggested_tier`
- `pipeline_stage`
- `expected_value`
- `probability`
- `expected_close_date`
- `stage_updated_at`
- `lost_reason`
- `notes`
- `updated_at`

### 4. Activity (Tab: Activities)
- `id` (UUID)
- `company_id` (FK)
- `contact_id` (FK)
- `employee_name`
- `type`
- `date`
- `subject`
- `notes`
- `outcome`
- `next_step`
- `next_meeting_date`
- `next_meeting_time`

### 5. Task (Tab: Tasks)
- `id` (UUID)
- `company_id` (FK)
- `description`
- `due_date`
- `due_time`
- `priority`
- `status`
- `completed_at`

### 6. ResearchSource (Tab: ResearchSources)
- `id` (UUID)
- `company_id` (FK)
- `source_url`
- `source_type`
- `retrieved_at`
- `publication_date`
- `field_name` (or claim_key)
- `evidence_text`
- `verification_status`

### 7. AIRecommendation (Tab: AIRecommendations)
- `id` (UUID)
- `company_id` (FK)
- `recommended_service`
- `recommended_tier`
- `reasoning`
- `discovery_questions`
- `model_provider`
- `model_name`
- `prompt_version`
- `created_at`
- `approval_status`

### 8. AuditLog (Tab: AuditLogs)
- `id` (UUID)
- `event_type`
- `entity_type`
- `entity_id`
- `action`
- `previous_value`
- `new_value`
- `created_at`

## Deduplication Strategy
- **Normalized Domain**: Strip `http://`, `https://`, `www.`, and trailing slashes. Use this as the primary unique key for companies.
- **Name Matching**: Basic string similarity for catching variations of the same company name. Warn user if a similar company exists before inserting.
