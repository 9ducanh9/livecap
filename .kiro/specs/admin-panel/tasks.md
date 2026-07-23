# Implementation Plan: Admin Panel

## Overview

The Admin Panel extends LiveCap's existing read-only `GET /api/admin/overview` endpoint into a full-featured multi-page admin experience. Implementation follows the phased delivery approach: Phase 1 (pagination, search, filtering), Phase 2 (mutating actions + audit logging), Phase 3 (usage analytics), Phase 4 (revenue dashboard + system health). The backend uses Python/FastAPI with new service modules, and the frontend uses React + TypeScript + Tailwind CSS with lazy-loaded admin sub-pages.

## Tasks

- [x] 1. Phase 1: Backend - Pagination, Search, and Filtering
  - [x] 1.1 Create `backend/app/services/admin_users.py` with user listing logic
    - Implement `list_users(page, page_size, search_email, filter_tier, filter_status)` function
    - Query Cognito `ListUsers` with pagination token handling
    - Join Cognito user data with DynamoDB usage table (`livecap-usage-dev`) for tier, sessions, minutes
    - Return `PaginatedUserList` with users, page metadata, and aggregate stats (total_users, per-tier counts)
    - Implement case-insensitive email search filtering against Cognito attributes
    - Implement tier and status filters applied after merging Cognito + DynamoDB data
    - Handle duplicate emails (native + federated) by including Identity_Provider field
    - Graceful degradation: return partial data if Cognito or DynamoDB fails
    - _Requirements: 2.1, 2.2, 2.3, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 9.3, 16.1_

  - [x] 1.2 Create `backend/app/services/admin_users.py` - user detail function
    - Implement `get_user_detail(cognito_username)` function
    - Query Cognito for user profile (email, status, created_date, identity_provider)
    - Query DynamoDB usage table for last 3 months of usage history
    - Query DynamoDB transcript-history table for recent session summaries
    - Return `UserDetail` model with profile, usage_history, transcript_sessions
    - Return HTTP 404 if user not found in Cognito
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [x] 1.3 Extend `backend/app/routers/admin.py` with Phase 1 endpoints
    - Add `GET /api/admin/users` endpoint with query params: page, page_size, search_email, filter_tier, filter_status
    - Add `GET /api/admin/users/{cognito_username}` endpoint for user detail
    - All endpoints use `Depends(require_admin_user)` for auth
    - Define Pydantic response models: `UserRecord`, `PaginatedUserList`, `UserStats`, `UserDetail`
    - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.3, 8.4, 8.5_

  - [x] 1.4 Write property tests for pagination and filtering logic
    - **Property 2: Pagination correctness** — For any set of users and valid page/page_size, verify at most page_size users returned, total_pages equals ceil(total/page_size), iterating all pages yields all users exactly once
    - **Property 4: Filter correctness** — For any combination of filters, verify returned set satisfies ALL active filters, and stats reflect the filtered set
    - **Validates: Requirements 2.1, 2.3, 3.1, 3.2, 3.3, 3.4, 3.5, 9.2**

  - [x] 1.5 Write unit tests for `admin_users.py` and Phase 1 router endpoints
    - Test user listing with mocked Cognito and DynamoDB responses
    - Test pagination edge cases (empty set, single page, last page partial)
    - Test search by email substring (case-insensitive)
    - Test combined filters (tier + status + email simultaneously)
    - Test user detail with valid and invalid cognito_username
    - Test graceful degradation when Cognito or DynamoDB is unreachable
    - _Requirements: 2.1, 2.2, 3.1, 3.2, 3.3, 8.5, 16.1_

- [x] 2. Phase 1: Frontend - User Management Page
  - [x] 2.1 Set up admin routing with React Router and lazy loading
    - Update `App.tsx` to use React Router with path-based routing for `/admin/*`
    - Create `AdminShell` layout component with sidebar navigation (Users, Usage, Revenue, System)
    - Implement lazy loading (React.lazy + Suspense) for each admin sub-page
    - Apply LiveCap design system: navy ink (#102247), emerald (#0a9c88), paper (#f7f8fc) backgrounds
    - Add active state indication on navigation links
    - Add "Back to workspace" link in navigation
    - Responsive layout (768px–1920px)
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 15.1, 15.2, 15.3, 15.4, 15.5_

  - [x] 2.2 Create shared admin UI components
    - Build `StatsCard` component (icon, label, value, sub-text) with LiveCap card styling (rounded-2xl, border #dce5f2)
    - Build `DataTable` component with pagination controls (page nav, page size selector)
    - Build `FilterBar` component with email search input + tier dropdown + status dropdown
    - Build `AdminNotification` toast component for success/error messages
    - Use lucide-react icons throughout
    - _Requirements: 9.1, 15.1, 15.2, 15.3, 15.4_

  - [x] 2.3 Build `AdminUsersPage` with user listing, stats cards, and filters
    - Display Stats_Cards: total users, Free count, Pro count, Business count
    - Display paginated DataTable with columns: email, tier, status, created date, last active
    - Wire FilterBar to query params and trigger API calls on change
    - Reset to page 1 when filters change
    - Show Identity_Provider column when duplicate emails exist
    - Show loading indicators per section independently
    - _Requirements: 2.4, 2.5, 3.5, 9.1, 9.2, 16.3_

  - [x] 2.4 Build user detail panel/sub-page
    - Display user profile info (email, tier, status, identity provider, created date)
    - Display monthly usage history (sessions, minutes) for last 3 months
    - Display recent transcript sessions list with date, duration, segment count
    - Display loading state while fetching detail data
    - _Requirements: 8.1, 8.2, 8.3_

  - [x] 2.5 Extend `frontend/src/services/adminService.ts` with Phase 1 API calls
    - Add `getUsers(params: UserListParams): Promise<PaginatedUsers>` function
    - Add `getUserDetail(username: string): Promise<UserDetail>` function
    - Define TypeScript interfaces for `UserRecord`, `PaginatedUsers`, `UserDetail`
    - Handle 401/403 errors with `AdminAccessError`
    - _Requirements: 2.1, 8.1_

  - [x] 2.6 Implement frontend admin access control
    - Check admin group membership on frontend after authentication
    - Show admin nav link only for admin users
    - Display access-denied message for non-admin users navigating to `/admin/*`
    - Provide link back to workspace from access-denied page
    - _Requirements: 1.4, 1.5_

- [x] 3. Checkpoint - Phase 1 complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Phase 2: Backend - Mutating Actions and Audit Logging
  - [x] 4.1 Create `backend/app/services/admin_audit.py` audit service
    - Implement `record_action(admin_user_id, target_user_id, action_type, previous_value, new_value)` function
    - Write audit entries to DynamoDB table `livecap-admin-audit`
    - Partition key: `TARGET#{cognito_username}`, Sort key: `TS#{ISO-timestamp}#{uuid-short}`
    - Set TTL at 365 days from creation
    - Implement `get_audit_entries_for_user(target_user_id, limit)` function
    - Return `AuditLogEntry` model with entry_id, admin_user_id, target_user_id, action_type, previous/new values, timestamp
    - _Requirements: 7.1, 7.2, 7.3_

  - [x] 4.2 Add mutation functions to `backend/app/services/admin_users.py`
    - Implement `disable_user(cognito_username)` — calls Cognito `AdminDisableUser`
    - Implement `enable_user(cognito_username)` — calls Cognito `AdminEnableUser`
    - Implement `reset_password(cognito_username)` — calls Cognito `AdminResetUserPassword`
    - Implement `change_tier(cognito_username, new_tier)` — updates DynamoDB usage table tier field
    - Validate tier values: only "free", "pro", "business" accepted; reject others with error
    - For tier change: also update usage quota limits to match new tier immediately
    - Detect federated-only users and reject password reset with appropriate error
    - Each mutation calls `admin_audit.record_action()` before returning success
    - If audit write fails: rollback the mutation (re-enable/re-disable, revert tier) and return 500
    - Check for active Stripe subscription on tier change and include warning in response
    - _Requirements: 4.1, 4.2, 4.4, 5.1, 5.2, 5.3, 5.5, 6.1, 6.2, 6.3, 6.4, 6.6, 7.1, 7.5_

  - [x] 4.3 Extend `backend/app/routers/admin.py` with mutation endpoints
    - Add `POST /api/admin/users/{cognito_username}/disable` endpoint
    - Add `POST /api/admin/users/{cognito_username}/enable` endpoint
    - Add `POST /api/admin/users/{cognito_username}/reset-password` endpoint
    - Add `POST /api/admin/users/{cognito_username}/change-tier` endpoint (body: `{"tier": "pro"}`)
    - Return appropriate HTTP status codes: 200 success, 404 user not found, 422 invalid tier, 500 audit failure, 502 Cognito error
    - Include audit log entries in user detail response
    - _Requirements: 4.1, 4.2, 5.1, 5.2, 6.1, 6.3, 7.4_

  - [x] 4.4 Write property tests for audit and mutation logic
    - **Property 5: Tier change validation** — For any valid tier value, change_tier updates persisted tier; for invalid values, returns error and tier unchanged
    - **Property 6: Stripe subscription warning** — For any user with active Stripe subscription, tier change response includes warning
    - **Property 7: Audit log completeness** — For any successful mutation, an audit entry is persisted with correct admin_user_id, target_user_id, action_type, and UTC timestamp
    - **Property 8: Audit failure blocks mutation** — When audit write fails, API returns error and user state remains unchanged
    - **Validates: Requirements 6.1, 6.2, 6.3, 6.6, 7.1, 7.2, 7.5**

  - [x] 4.5 Write unit tests for mutation and audit endpoints
    - Test disable/enable with mocked Cognito calls
    - Test password reset success and federated-user rejection
    - Test tier change with valid and invalid tier values
    - Test audit log creation on each mutation type
    - Test audit failure rollback behavior
    - Test Stripe subscription warning on tier change
    - _Requirements: 4.1, 4.2, 4.4, 5.1, 5.3, 5.5, 6.1, 6.3, 6.6, 7.1, 7.5_

- [x] 5. Phase 2: Frontend - Mutation Actions UI
  - [x] 5.1 Add mutation actions to `AdminUsersPage` and user detail panel
    - Add disable/enable toggle button per user row (updates UI without full reload)
    - Add "Reset Password" button (disabled for federated-only users)
    - Add "Change Tier" dropdown/modal with Free/Pro/Business options
    - Show `ConfirmDialog` modal before destructive actions (disable, tier change)
    - Display Stripe subscription warning when changing tier for subscribed users
    - Show success/error notifications via `AdminNotification` component
    - Display audit log section in user detail view
    - _Requirements: 4.5, 5.4, 6.5, 6.6, 7.4, 16.2_

  - [x] 5.2 Extend `adminService.ts` with mutation API calls
    - Add `disableUser(username)`, `enableUser(username)` functions
    - Add `resetPassword(username)` function
    - Add `changeTier(username, tier)` function
    - Handle error responses and surface error messages to UI
    - _Requirements: 4.1, 5.1, 6.1_

- [x] 6. Checkpoint - Phase 2 complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Phase 3: Backend - Usage Analytics
  - [x] 7.1 Create `backend/app/services/admin_analytics.py`
    - Implement `get_monthly_usage(start_month, end_month)` — scan DynamoDB usage table, aggregate sessions/minutes/unique users per month
    - Implement `get_top_users(month, limit=10)` — return top N users by minutes_used, sorted descending
    - Implement `get_tier_distribution()` — count users per tier, calculate percentages
    - Enforce 90-day lookback limit (no data beyond 90 days due to DynamoDB TTL)
    - Default to current month when no date range provided
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 11.1, 11.2, 11.3_

  - [x] 7.2 Extend `backend/app/routers/admin.py` with analytics endpoints
    - Add `GET /api/admin/usage` endpoint with optional query params: start_month, end_month
    - Add `GET /api/admin/usage/top-users` endpoint with optional query param: month
    - Return Pydantic models: `MonthlyUsageData`, `TopUserRow`, `TierDistribution`
    - _Requirements: 10.1, 11.1, 11.3_

  - [x] 7.3 Write property tests for analytics aggregation
    - **Property 9: Usage aggregation correctness** — For any set of per-user usage records, total_sessions equals sum of individual sessions, total_minutes equals sum of individual minutes, unique_active_users equals count of distinct users with sessions > 0
    - **Property 10: Date range filtering** — For any valid date range, all returned months fall within range, no months outside range included
    - **Property 11: Top users ranking** — Top users sorted descending by minutes_used, at most 10 entries, each includes email/tier/sessions/minutes
    - **Property 12: Tier distribution consistency** — Tier counts sum to total users, percentages equal (count/total)*100, zero users means zero percentages
    - **Validates: Requirements 10.1, 10.2, 10.4, 11.1, 11.2, 11.3**

- [x] 8. Phase 3: Frontend - Usage Analytics Page
  - [x] 8.1 Build `AdminUsagePage` component
    - Display monthly totals: total sessions, total minutes, unique active users
    - Display usage trend visualization (line/bar chart) for sessions and minutes over time
    - Display top 10 users table: email, tier, sessions_used, minutes_used
    - Display tier distribution breakdown (count and percentage per tier)
    - Add date range filter (limit to 90-day window with explanatory note)
    - Show loading indicators per section
    - _Requirements: 10.1, 10.2, 10.4, 10.5, 11.1, 11.2, 11.3, 11.4, 16.3_

  - [x] 8.2 Extend `adminService.ts` with analytics API calls
    - Add `getUsageAnalytics(params?: DateRangeParams)` function
    - Add `getTopUsers()` function
    - Define TypeScript interfaces for `UsageAnalytics`, `TopUser`, `TierDistribution`
    - _Requirements: 10.1, 11.1_

- [x] 9. Checkpoint - Phase 3 complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Phase 4: Backend - Revenue and System Health
  - [x] 10.1 Create `backend/app/services/admin_revenue.py`
    - Implement `get_revenue_metrics()` — query Stripe Subscriptions API for active subs, calculate MRR from actual recurring amounts
    - Implement `get_recent_transactions(limit=20)` — query Stripe for recent charges/refunds
    - Count churned subscriptions (canceled in last 30 days)
    - Return `RevenueMetrics` model with mrr_usd, active_subscriptions, churned_subscriptions, recent_transactions
    - Graceful degradation: return `stripe_data_available=False` + warning if Stripe API unreachable
    - _Requirements: 12.1, 12.2, 12.3, 12.5_

  - [x] 10.2 Create `backend/app/services/admin_health.py`
    - Implement `get_system_health()` — query ECS DescribeServices, CloudWatch DescribeAlarms, Cost Explorer GetCostAndUsage
    - ECS: return running_count, desired_count, pending_count, health_status
    - CloudWatch: return list of alarms with state (OK/ALARM/INSUFFICIENT_DATA) and reason
    - Cost Explorer: call in us-east-1 region per AWS requirement, return current_month_usd + data_timestamp
    - Graceful degradation: each service fails independently, include warnings list for failed services
    - _Requirements: 13.1, 13.2, 13.4, 13.5, 13.6, 13.7, 16.1_

  - [x] 10.3 Extend `backend/app/routers/admin.py` with revenue and health endpoints
    - Add `GET /api/admin/revenue` endpoint returning revenue metrics
    - Add `GET /api/admin/system` endpoint returning system health data
    - Define Pydantic response models: `RevenueMetrics`, `StripeTransaction`, `SystemHealth`, `EcsStatus`, `CloudWatchAlarm`, `CostEstimate`
    - _Requirements: 12.1, 13.1_

  - [x] 10.4 Write integration tests for revenue and health services
    - Test revenue calculation with mocked Stripe responses
    - Test system health with mocked ECS, CloudWatch, Cost Explorer responses
    - Test graceful degradation when individual services are unreachable
    - **Property 13: Graceful degradation** — For any subset of failing AWS services, response contains all data from non-failing services plus warnings identifying each failed service
    - **Validates: Requirements 12.5, 13.4, 16.1**

- [x] 11. Phase 4: Frontend - Revenue and System Health Pages
  - [x] 11.1 Build `AdminRevenuePage` component
    - Display Stats_Cards: MRR, active subscriptions, churned subscriptions
    - Display recent transactions table: date, user email, amount, transaction type
    - Add "Open Stripe Dashboard" link (opens in new tab)
    - Show warning banner when Stripe data is incomplete/unavailable
    - _Requirements: 12.1, 12.3, 12.4, 12.5_

  - [x] 11.2 Build `AdminSystemPage` component
    - Display ECS status: running tasks, desired tasks, health indicator (green/yellow/red)
    - Display CloudWatch alarms list with state indicators
    - Display current month cost estimate with data timestamp label
    - Add quick-link buttons for AWS Console dashboards (ECS, CloudWatch, Cost Explorer) opening in new tabs
    - Show warning banners for services that could not be queried
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6_

  - [x] 11.3 Extend `adminService.ts` with revenue and system API calls
    - Add `getRevenue()` function returning `RevenueData`
    - Add `getSystemHealth()` function returning `SystemHealth`
    - Define TypeScript interfaces for response types
    - Handle partial data / warning fields in responses
    - _Requirements: 12.1, 13.1_

- [x] 12. Integration and Wiring
  - [x] 12.1 Wire all admin pages together and verify routing
    - Ensure all admin routes (`/admin/users`, `/admin/usage`, `/admin/revenue`, `/admin/system`) load correctly
    - Verify lazy loading and code splitting works for each sub-page
    - Verify admin auth guard blocks non-admin users at both frontend and backend level
    - Ensure the existing `GET /api/admin/overview` endpoint remains unchanged and functional
    - Test network error handling with retry option on frontend
    - _Requirements: 1.1, 1.4, 1.5, 14.1, 14.2, 16.4_

  - [x] 12.2 Write property test for admin authorization gate
    - **Property 1: Admin authorization gate** — For any request to any admin endpoint by a non-admin caller (no token, invalid token, valid token for non-admin user), the API rejects with 401 or 403 without executing endpoint logic
    - **Validates: Requirements 1.1, 1.2, 1.3**

  - [x] 12.3 Write end-to-end integration tests
    - Test full user management flow: list → filter → detail → disable → enable
    - Test tier change with audit log verification
    - Test usage analytics with date range filtering
    - Test revenue endpoint with mocked Stripe
    - Test system health endpoint with partial service failures
    - _Requirements: 1.1, 2.1, 4.1, 6.1, 10.1, 12.1, 13.1_

- [x] 13. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation at the end of each phase
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The existing `GET /api/admin/overview` endpoint is preserved unchanged throughout
- Backend implementation uses Python (FastAPI + boto3 + Pydantic)
- Frontend implementation uses TypeScript (React + Tailwind CSS + lucide-react)
- DynamoDB table `livecap-admin-audit` must be created (via Terraform or manually) before Phase 2 implementation

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "2.1", "2.2"] },
    { "id": 1, "tasks": ["1.3", "2.5", "2.6"] },
    { "id": 2, "tasks": ["1.4", "1.5", "2.3", "2.4"] },
    { "id": 3, "tasks": ["4.1", "4.2"] },
    { "id": 4, "tasks": ["4.3", "5.2"] },
    { "id": 5, "tasks": ["4.4", "4.5", "5.1"] },
    { "id": 6, "tasks": ["7.1"] },
    { "id": 7, "tasks": ["7.2", "8.2"] },
    { "id": 8, "tasks": ["7.3", "8.1"] },
    { "id": 9, "tasks": ["10.1", "10.2"] },
    { "id": 10, "tasks": ["10.3", "11.3"] },
    { "id": 11, "tasks": ["10.4", "11.1", "11.2"] },
    { "id": 12, "tasks": ["12.1"] },
    { "id": 13, "tasks": ["12.2", "12.3"] }
  ]
}
```
