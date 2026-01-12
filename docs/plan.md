### Vision: The same day that a solution for a new issue is posted in an AVA thread or ICM, we have a TSG draft PR up in the relevant wiki and ready for review.

---

## Plan: AVA Channel Analyzer & Wiki PR Integration

Add a background service that scans AVA Teams channels for new troubleshooting issues, compares them against existing wiki TSGs, queues novel findings for review, and enables one-click PR submission to the Azure DevOps Wiki after TSG creation.

### Steps

1. **Create AVA scanner module** in `ava-analyzer/scanner/` with `teams_client.py` (Microsoft Graph API for channel access), `ava_parser.py` (parse posts into structured format), and `scheduler.py` (APScheduler for periodic background scans).

2. **Create novelty comparison module** in `ava-analyzer/comparison/` with `wiki_client.py` (fetch existing TSGs from ADO Wiki), `novelty_agent.py` (AI agent for detailed comparison), and `embeddings.py` (vector similarity for fast initial filtering).

3. **Create persistent queue system** in `ava-analyzer/queue/` with `models.py` (dataclass/SQLAlchemy models for queue items with status: pending/approved/rejected/pr_created), `store.py` (SQLite persistence), and `manager.py` (CRUD operations).

4. **Create integration adapters** in `ava-analyzer/integration/` with `pipeline_adapter.py` (wrapper to call existing `run_pipeline()` with AVA post content as notes) and `pr_creator.py` (Azure DevOps API to create branches, commit TSGs, open PRs).

5. **Add API routes** via Flask Blueprint in `ava-analyzer/api/routes.py` for endpoints: `/api/ava/queue` (list items), `/api/ava/queue/<id>` (view/update), `/api/ava/queue/<id>/approve` (trigger TSG generation), `/api/ava/submit-pr` (create wiki PR), `/api/ava/scan` (manual trigger).

6. **Extend UI** in `templates/index.html` with a new "AVA Queue" tab showing pending/reviewed items, side-by-side view of AVA post vs generated TSG, and "Submit PR" button after TSG approval.

### Open Items

- **Teams API authentication**: TBD - need to determine delegated vs application auth approach for Microsoft Graph API access to AVA channels.

---

#### Post-draft

Extend TSG Builder with the ability to create pull requests for new TSGs on wikis

#### Pre-draft

Build a service that reviews AVA channels on a regular basis for new TSG subjects (which could then trigger the tsgbuilder) 
 
- scan AVA for all recent posts
- if solution is offered, see if information seems "new" (compare against info already in TSGs in wikis)
- if info doesn't exist, kick off tsgbuilder based on AVA content and create PR for new TSG for review
 
We can kick off an agent that compares the solution thread against existing TSGs in a research fashion. Then, if it passes criteria, we've identified a new TSG could be added and the AVA thread is a logical place to get the input notes to kick off tsgbuilder.
