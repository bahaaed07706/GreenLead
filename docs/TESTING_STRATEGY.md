# Testing Strategy

To ensure reliability, the following testing layers will be implemented using **Pytest**:

## 1. Unit Tests
- **Service Matching Engine**: Test the deterministic rules against mock JSON inputs to ensure correct service and tier assignments.
- **Score Calculation**: Test edge cases for Fit and Confidence scores.
- **Domain Normalization**: Test deduplication logic (e.g., `http://www.example.com` equals `example.com/`).

## 2. Integration Tests
- **Repository Tests**: Verify CRUD operations against a mock Google Sheet or a dedicated "Test" sheet environment.
- **API/Route Tests**: Ensure all endpoints require authentication and handle invalid payloads gracefully via FastAPI test client.

## 3. AI & Search Testing
- **Structured Output Validation**: Mock the AI provider responses to ensure the application handles missing fields, hallucinated fields, or malformed JSON without crashing (Pydantic validation).
- **Prompt Injection Tests**: Feed malicious text into the extraction pipeline to ensure the AI does not deviate from its extraction task.

## 4. End-to-End & UAT
- **User Acceptance Testing (UAT)**: The final deliverable requires testing 10 real companies through the full pipeline (Search -> Extract -> Review -> Save -> Dashboard). This also serves as the final evaluation for AI Provider selection.
- **Deployment Smoke Tests**: Ensure the app boots correctly on Render/Railway and connects to external APIs.
