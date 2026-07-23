# Requirements Document

## Introduction

The Admin Panel is a comprehensive administrative dashboard for LiveCap, a real-time bilingual speech caption and translation B2C SaaS application. The panel provides authorized administrators with full visibility into user management, usage analytics, revenue and subscriptions, and system health. It extends the existing read-only v1 admin overview endpoint (`GET /api/admin/overview`, commit 8dc7167) into a multi-page admin experience with actionable controls (disable/enable users, reset passwords, change tiers) and detailed analytics views. Only users belonging to the Cognito "admin" group may access admin functionality; all other users are denied access with appropriate error responses.

The Admin Panel is accessed via `/admin/*` routes on the frontend and `/api/admin/*` endpoints on the backend. It integrates with existing infrastructure: Amazon Cognito (user pool and admin group), DynamoDB (livecap-sessions-dev, livecap-transcript-history-dev, livecap-usage-dev tables), Stripe (subscription and payment data), and ECS Fargate (system health).

### Phased Delivery

This feature expands substantially on the existing read-only v1 endpoint. Delivery is split into phases so that each phase's Terraform IAM changes can be reviewed and applied independently rather than as one large plan:

- **Phase 1:** Pagination, search, and filtering on the existing user overview.
- **Phase 2:** Mutating user actions (disable/enable, reset password, tier change) and audit logging.
- **Phase 3:** Usage analytics (monthly totals, top users, tier distribution, trends).
- **Phase 4:** Revenue dashboard (MRR from Stripe, transactions) and system health (ECS, CloudWatch, Cost Explorer).

## Glossary

- **Admin_Panel**: The collection of frontend pages and backend endpoints that provide administrative capabilities for LiveCap.
- **Admin_User**: A user whose Cognito account belongs to the "admin" group and is authorized to access Admin_Panel functionality.
- **Admin_API**: The set of backend REST endpoints under the `/api/admin` prefix that serve admin data and execute admin actions.
- **User_Management_Page**: The frontend page at `/admin/users` that displays and manages all LiveCap users.
- **Usage_Analytics_Page**: The frontend page at `/admin/usage` that displays aggregated usage metrics and trends.
- **Revenue_Page**: The frontend page at `/admin/revenue` that displays subscription and revenue information.
- **System_Health_Page**: The frontend page at `/admin/system` that displays ECS service status and operational health indicators.
- **Admin_Auth_Middleware**: The backend dependency that validates the caller's JWT and confirms Cognito "admin" group membership before allowing access to Admin_API endpoints.
- **User_Record**: The combined data for a single LiveCap user, including Cognito attributes (email, status, created date, last active) and DynamoDB usage data (tier, sessions, minutes, subscription status).
- **Stats_Card**: A summary metric display component showing a single aggregate value with a label and supporting detail.
- **Tier**: The subscription level assigned to a user (Free, Pro, or Business), determining usage quotas.
- **MRR**: Monthly Recurring Revenue, calculated from the count of active paid subscriptions multiplied by their respective tier prices.
- **Pagination**: The mechanism for loading large datasets in discrete pages of configurable size rather than all at once.
- **Audit_Log_Entry**: A record persisted for every mutating admin action, containing: admin user ID, target user ID, action type, previous value (where applicable), new value, and UTC timestamp.
- **Cognito_Username**: The unique identifier for a user within the Cognito User Pool. For native email/password accounts this equals the email; for federated accounts (e.g., Google OAuth) this is a provider-prefixed value like `Google_<sub>`, which is distinct from the email attribute.
- **Identity_Provider**: The authentication method associated with a Cognito user account (native email/password or a federated provider such as Google).

## Requirements

### Requirement 1: Admin Authorization

**User Story:** As a platform operator, I want only admin-group members to access admin functionality, so that sensitive user data and system controls are protected from unauthorized access.

#### Acceptance Criteria

1. WHEN a request arrives at any Admin_API endpoint, THE Admin_Auth_Middleware SHALL validate the caller's Cognito access token and confirm membership in the "admin" group before processing the request.
2. IF the request does not include a valid Cognito access token, THEN THE Admin_API SHALL return an HTTP 401 response with a message indicating sign-in is required.
3. IF the caller's Cognito account is not a member of the "admin" group, THEN THE Admin_API SHALL return an HTTP 403 response with a message indicating admin access is required.
4. WHEN a user is authenticated on the frontend, THE Frontend SHALL check admin group membership and display the admin navigation link only for Admin_User accounts.
5. IF a non-admin user navigates to any `/admin/*` route in the browser, THEN THE Frontend SHALL display an access-denied message and provide a link back to the workspace.

### Requirement 2: User Listing with Pagination

**User Story:** As an admin, I want to see a paginated list of all users with their key attributes, so that I can quickly scan the user base without loading performance issues.

#### Acceptance Criteria

1. WHEN an Admin_User navigates to the User_Management_Page, THE Admin_API SHALL return a paginated list of User_Records.
2. THE Admin_API SHALL return each User_Record containing: email, tier, account status (enabled or disabled), created date, and last active date.
3. WHEN the Admin_API returns a paginated response, THE Admin_API SHALL include the current page number, total page count, and total user count.
4. WHEN the User_Management_Page loads, THE Frontend SHALL display the first page of users with a default page size of 20 records.
5. WHEN an Admin_User navigates to the next or previous page, THE Frontend SHALL request and display the corresponding page of User_Records from the Admin_API.

### Requirement 3: User Search and Filtering

**User Story:** As an admin, I want to search and filter users by email, tier, or status, so that I can quickly find specific users or user segments.

#### Acceptance Criteria

1. WHEN an Admin_User enters a search term in the email search field, THE Admin_API SHALL return only User_Records whose email contains the search term (case-insensitive).
2. WHEN an Admin_User selects a tier filter, THE Admin_API SHALL return only User_Records matching the selected tier (Free, Pro, or Business).
3. WHEN an Admin_User selects a status filter, THE Admin_API SHALL return only User_Records matching the selected account status (enabled or disabled).
4. WHEN multiple filters are active simultaneously, THE Admin_API SHALL return only User_Records that satisfy all active filters.
5. WHEN filters are applied, THE Admin_API SHALL reset pagination to the first page and include updated total counts in the response.
6. IF a search by email matches more than one Cognito user record (e.g., a native and a federated identity sharing the same email attribute), THEN THE Admin_API SHALL return all matching User_Records distinguished by their Cognito_Username, and THE User_Management_Page SHALL display the Identity_Provider for each row.

### Requirement 4: User Actions - Disable and Enable

**User Story:** As an admin, I want to disable or enable user accounts, so that I can manage access for users who violate policies or request reactivation.

#### Acceptance Criteria

1. WHEN an Admin_User requests to disable a user account, THE Admin_API SHALL call Cognito AdminDisableUser targeting the user by Cognito_Username and return confirmation of success.
2. WHEN an Admin_User requests to enable a previously disabled user account, THE Admin_API SHALL call Cognito AdminEnableUser targeting the user by Cognito_Username and return confirmation of success.
3. WHEN a user account is disabled through the Admin_API, THE disabled user SHALL be unable to authenticate with LiveCap until the account is re-enabled.
4. IF the Cognito disable or enable operation fails, THEN THE Admin_API SHALL return an error response describing the failure reason.
5. WHEN a disable or enable action succeeds, THE User_Management_Page SHALL update the displayed status of the affected user without requiring a full page reload.

### Requirement 5: User Actions - Reset Password

**User Story:** As an admin, I want to trigger a password reset for a user, so that I can help users who are locked out of their accounts.

#### Acceptance Criteria

1. WHEN an Admin_User requests a password reset for a user, THE Admin_API SHALL call Cognito AdminResetUserPassword targeting the user by Cognito_Username.
2. WHEN the password reset is initiated successfully, THE Admin_API SHALL return confirmation that a reset email has been sent to the user.
3. IF the Cognito password reset operation fails, THEN THE Admin_API SHALL return an error response describing the failure reason.
4. WHEN a password reset action succeeds, THE User_Management_Page SHALL display a confirmation notification to the Admin_User.
5. IF the target user's Cognito account has no native password (federated-only, e.g., Google Identity_Provider), THEN THE Admin_API SHALL return an error indicating password reset is not applicable, and THE User_Management_Page SHALL disable the reset-password action for that user rather than allow the request.

### Requirement 6: User Actions - Change Tier

**User Story:** As an admin, I want to manually change a user's subscription tier bypassing the payment flow, so that I can grant complimentary upgrades or handle special cases.

#### Acceptance Criteria

1. WHEN an Admin_User requests a tier change for a user, THE Admin_API SHALL update the user's tier in the DynamoDB usage table to the specified tier (Free, Pro, or Business).
2. WHEN a tier change is applied, THE Admin_API SHALL update the user's usage quotas to match the new tier limits immediately.
3. THE Admin_API SHALL accept tier change requests only for valid tier values (free, pro, or business) and SHALL return an error for invalid values.
4. WHEN a tier change succeeds, THE Admin_API SHALL return the updated User_Record reflecting the new tier.
5. WHEN a tier change action succeeds, THE User_Management_Page SHALL update the displayed tier of the affected user without requiring a full page reload.
6. IF the target user has an active Stripe subscription and an admin manually changes their tier, THEN THE Admin_API SHALL include a warning in the response noting that the change does not modify the underlying Stripe subscription, and THE User_Management_Page SHALL surface this warning to the admin before confirming the action.

### Requirement 7: Audit Logging for Admin Actions

**User Story:** As a platform operator, I want every mutating admin action recorded in an audit trail, so that I can trace who changed what, when, and revert mistakes if necessary.

#### Acceptance Criteria

1. WHEN an Admin_User performs a disable, enable, reset-password, or tier-change action, THE Admin_API SHALL persist an Audit_Log_Entry before returning success.
2. THE Audit_Log_Entry SHALL contain: admin user ID, target user ID, action type, previous value (where applicable), new value, and UTC timestamp.
3. THE Admin_API SHALL store Audit_Log_Entries in a DynamoDB table dedicated to admin audit records.
4. WHEN the User_Management_Page displays user detail, THE Frontend SHALL include a section showing recent Audit_Log_Entries for that user.
5. IF persisting the Audit_Log_Entry fails, THEN THE Admin_API SHALL reject the entire action and return an error, ensuring no un-audited mutations occur.

### Requirement 8: User Detail View

**User Story:** As an admin, I want to view detailed usage statistics and transcript history for a specific user, so that I can investigate support issues and understand user behavior.

#### Acceptance Criteria

1. WHEN an Admin_User selects a user from the User_Management_Page, THE Frontend SHALL display a detail view containing the user's profile, usage statistics, and transcript history.
2. THE user detail view SHALL display usage statistics including: total sessions this month, total minutes this month, sessions remaining (for quota-limited tiers), and historical monthly usage.
3. THE user detail view SHALL display the user's transcript history with session date, duration, and segment count for each session.
4. WHEN the Admin_API retrieves user detail data, THE Admin_API SHALL query the livecap-usage-dev and livecap-transcript-history-dev DynamoDB tables for the specified user.
5. IF the specified user does not exist, THEN THE Admin_API SHALL return an HTTP 404 response.

### Requirement 9: User Statistics Cards

**User Story:** As an admin, I want to see summary statistics about the user base at a glance, so that I can quickly assess the platform's adoption metrics.

#### Acceptance Criteria

1. WHEN the User_Management_Page loads, THE Frontend SHALL display Stats_Cards showing: total users, Free tier count, Pro tier count, and Business tier count.
2. THE Stats_Cards SHALL reflect the filtered user set when filters are active on the User_Management_Page.
3. THE Admin_API SHALL include aggregate statistics (total users and per-tier counts) in the user listing response.

### Requirement 10: Usage Analytics - Monthly Totals

**User Story:** As an admin, I want to see monthly usage totals, so that I can track platform utilization over time.

#### Acceptance Criteria

1. WHEN an Admin_User navigates to the Usage_Analytics_Page, THE Admin_API SHALL return aggregated monthly usage data.
2. THE Admin_API SHALL return monthly totals including: total sessions, total minutes consumed, and count of unique active users for the selected period.
3. WHEN no date range filter is applied, THE Admin_API SHALL return usage data for the current calendar month.
4. WHEN a date range filter is applied, THE Admin_API SHALL return usage data aggregated across the specified date range.
5. THE Usage_Analytics_Page SHALL NOT display or request trend data older than 90 days, and SHALL indicate that historical data beyond this window is unavailable due to DynamoDB TTL expiration on monthly usage items.

### Requirement 11: Usage Analytics - Top Users and Distribution

**User Story:** As an admin, I want to see which users consume the most resources and how usage distributes across tiers, so that I can identify power users and plan capacity.

#### Acceptance Criteria

1. WHEN the Usage_Analytics_Page loads, THE Admin_API SHALL return a list of the top 10 users by total minutes used in the current month.
2. THE top users list SHALL include: email, tier, sessions used, and minutes used for each user.
3. WHEN the Usage_Analytics_Page loads, THE Admin_API SHALL return the tier distribution showing the count and percentage of users in each tier.
4. WHEN the Usage_Analytics_Page loads, THE Frontend SHALL display a usage trend visualization that shows sessions and minutes over time for the selected date range.

### Requirement 12: Revenue and Subscriptions

**User Story:** As an admin, I want visibility into revenue metrics and subscription health, so that I can monitor business performance.

#### Acceptance Criteria

1. WHEN an Admin_User navigates to the Revenue_Page, THE Admin_API SHALL return revenue metrics including: current MRR, count of active subscriptions, and count of churned subscriptions.
2. THE Admin_API SHALL calculate MRR by querying the Stripe Subscriptions API directly for active subscriptions and summing their actual recurring amounts, rather than deriving MRR from internal DynamoDB tier counts, so that coupons, discounts, and proration are accurately reflected. This incurs one external API call per page load.
3. WHEN the Revenue_Page loads, THE Frontend SHALL display a table of recent Stripe transactions including: date, user email, amount, and transaction type (payment, refund, or subscription change).
4. THE Revenue_Page SHALL display a link that opens the Stripe Dashboard in a new browser tab for detailed financial management.
5. IF the Stripe API is unreachable, THEN THE Admin_API SHALL return the available data with a warning indicating that Stripe data may be incomplete.

### Requirement 13: System Health Monitoring

**User Story:** As an admin, I want to see the operational health of LiveCap's infrastructure at a glance, so that I can detect and respond to issues quickly.

#### Acceptance Criteria

1. WHEN an Admin_User navigates to the System_Health_Page, THE Admin_API SHALL return ECS service status including: running task count, desired task count, and overall health status.
2. WHEN the System_Health_Page loads, THE Admin_API SHALL return a list of recent CloudWatch alarms with their current state (OK, ALARM, or INSUFFICIENT_DATA).
3. THE System_Health_Page SHALL display quick-link buttons that open the relevant AWS Console dashboards (ECS, CloudWatch, Cost Explorer) in new browser tabs.
4. IF the ECS or CloudWatch APIs are unreachable, THEN THE Admin_API SHALL return partial data with a warning indicating which services could not be queried.
5. WHEN the System_Health_Page loads, THE Frontend SHALL display a cost estimate for the current month based on available AWS Cost Explorer data.
6. THE cost estimate SHALL be labeled with its data timestamp so that it is not mistaken for a real-time figure, since AWS Cost Explorer data typically lags approximately 24 hours.
7. THE Admin_API SHALL call the AWS Cost Explorer API in the us-east-1 region regardless of the primary deployment region, per AWS's requirement that Cost Explorer is only accessible via that region.

### Requirement 14: Admin Navigation

**User Story:** As an admin, I want clear navigation between admin sections, so that I can move efficiently between user management, analytics, revenue, and system views.

#### Acceptance Criteria

1. WHILE an Admin_User is on any Admin_Panel page, THE Frontend SHALL display a persistent navigation sidebar or tab bar with links to: Users, Usage, Revenue, and System sections.
2. WHEN an Admin_User clicks a navigation link, THE Frontend SHALL load the corresponding admin section without a full page reload.
3. THE Admin_Panel navigation SHALL visually indicate which section is currently active.
4. THE Admin_Panel navigation SHALL include a link back to the main LiveCap workspace.

### Requirement 15: Admin Panel Visual Design

**User Story:** As an admin, I want the admin panel to match LiveCap's existing design system, so that the experience feels consistent and professional.

#### Acceptance Criteria

1. THE Admin_Panel SHALL use the LiveCap design system colors: navy ink (#102247) for text, emerald (#0a9c88) for primary accents, and paper (#f7f8fc) for page backgrounds.
2. THE Admin_Panel SHALL use Tailwind CSS utility classes consistent with the existing LiveCap frontend.
3. THE Admin_Panel SHALL use lucide-react icons consistent with the existing LiveCap frontend.
4. THE Admin_Panel SHALL use the existing LiveCap card styling: rounded-2xl borders with border color #dce5f2 and subtle shadow.
5. THE Admin_Panel SHALL be responsive, displaying correctly on viewport widths from 768px to 1920px.

### Requirement 16: Error Handling and Graceful Degradation

**User Story:** As an admin, I want the admin panel to handle errors gracefully when AWS services are unavailable, so that I can still access available information during partial outages.

#### Acceptance Criteria

1. IF any individual AWS service call (Cognito, DynamoDB, ECS, CloudWatch) fails during an Admin_API request, THEN THE Admin_API SHALL return the data that was successfully retrieved along with a warning identifying the failed service.
2. IF a user action (disable, enable, reset password, change tier) fails, THEN THE Frontend SHALL display an error notification describing the failure and the affected user SHALL remain in the previous state.
3. WHEN the Admin_Panel is loading data, THE Frontend SHALL display loading indicators for each section independently so that successfully loaded sections are visible while others continue loading.
4. IF the entire Admin_API is unreachable, THEN THE Frontend SHALL display a connection error message with a retry option.
