PHASE1_INVESTIGATE = """You are investigating a bug or feature request for Docyt.

## Task
1. Read the Slack thread context provided below for full details
2. Search the relevant codebase to understand the affected area
3. For bugs: find the root cause (RCA) — trace through the code
4. For features: understand requirements and scope
5. Search Jira for an existing ticket matching this issue
6. If no ticket exists, prepare a new ticket payload:
   - Project: ENG
   - Status: To Do
   - Team: AI/ML
   - Assignee: {jira_email}
   - Auto-detect: priority, platform, work type from context
7. Use `create_approval` tool with type `jira_ticket` to request approval before creating

## Issue Context
{issue_description}

## Source
{source_context}

## Service Conventions
{context}

## Skills
{skills}

## Important
- First sync the repo to latest master using git fetch/pull
- Save your investigation findings — they will be needed by the next phase
"""

PHASE2_PLAN = """You are brainstorming and planning implementation for a Docyt issue.

## Task
1. Review the investigation findings below
2. Brainstorm: explore the problem space, consider edge cases, alternative approaches, trade-offs, dependencies, risks
3. Write a step-by-step implementation plan including:
   - Files to modify/create
   - Approach for each change
   - Testing strategy (happy path, edge cases, negative scenarios, error handling)
4. Review the plan for gaps
5. Use `create_approval` tool with type `plan_approval` to request approval before implementation

## Investigation Findings
{investigation}

## Jira Ticket
{jira_key}

## Service Conventions
{context}

## Skills
{skills}
"""

PHASE3_IMPLEMENT = """You are implementing a planned change for Docyt.

## Task
1. Create branch `{jira_key}` from latest master
2. Set up git worktree if needed
3. Follow the approved plan step by step
4. Write tests covering: happy path, edge cases, negative scenarios, error handling
5. Run the test suite and fix any failures
6. Run linting
7. Self-review the code
8. Use `create_approval` tool with type `pr_creation` to request approval before creating the PR

## Approved Plan
{plan}

## Jira Ticket
{jira_key}

## Service Conventions
{context}

## Skills
{skills}

## User Preferences
{memory}
"""

PHASE4_PR = """You are creating a pull request and notifying the team.

## Task
1. Create a Bitbucket PR with:
   - Title linking to {jira_key}
   - Description summarizing changes
   - Link to Jira ticket
2. Message Sangram in #ai-ml channel on Slack asking for review
3. Log to Obsidian daily log
4. Send ntfy notification: "PR ready for {jira_key}"

## PR Details
{pr_details}

## Jira Ticket
{jira_key}

## Skills
{skills}
"""


def build_phase1_prompt(
    issue_description: str,
    source_context: str,
    context: str,
    skills: str,
    jira_email: str,
) -> str:
    return PHASE1_INVESTIGATE.format(
        issue_description=issue_description,
        source_context=source_context,
        context=context,
        skills=skills,
        jira_email=jira_email,
    )


def build_phase2_prompt(
    investigation: str,
    jira_key: str,
    context: str,
    skills: str,
) -> str:
    return PHASE2_PLAN.format(
        investigation=investigation,
        jira_key=jira_key,
        context=context,
        skills=skills,
    )


def build_phase3_prompt(
    plan: str,
    jira_key: str,
    context: str,
    skills: str,
    memory: str,
) -> str:
    return PHASE3_IMPLEMENT.format(
        plan=plan,
        jira_key=jira_key,
        context=context,
        skills=skills,
        memory=memory,
    )


def build_phase4_prompt(
    pr_details: str,
    jira_key: str,
    skills: str,
) -> str:
    return PHASE4_PR.format(
        pr_details=pr_details,
        jira_key=jira_key,
        skills=skills,
    )
