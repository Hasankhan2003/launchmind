# LaunchMind 🚀

LaunchMind is an AI-powered Multi-Agent Startup Accelerator System designed to completely automate the initial stages of a product launch. This system consists of fully autonomous AI agents that communicate over a structured JSON message bus to collaboratively go from a raw idea to a deployed product feature with real-world API interactions.

## 🧠 System Architecture

The core of the system is the **MessageBus**, handling structured JSON messages between agents based on a synchronized execution loop.

### Autonomous Agents
- **👑 CEO Agent (`ceo_agent.py`)**: The orchestrator. It receives a raw startup idea, decomposes it into tasks for sub-agents, and critically, acts as the quality gate performing LLM-based evaluations with an integrated feedback loop (dispatching `revision_request` messages).
- **📦 Product Agent (`product_agent.py`)**: Responsible for constructing the formal product specifications including value proposition, target personas, prioritized features, user stories, layout planning, and tone details.
- **💻 Engineer Agent (`engineer_agent.py`)**: Given a product specification, generates the UI/frontend HTML, interacts with the **GitHub REST API** to push commits, creates new branches, tracks progress via GitHub issues, and auto-submits Pull Requests.
- **📢 Marketing Agent (`marketing_agent.py`)**: Crafts compelling copy, taglines, and social posts. Executes targeted cold emails via the **SendGrid API** and posts rich notifications to workspaces using the **Slack Block Kit** API.
- **🔍 QA Agent (`qa_agent.py`)**: Conducts automated audits of HTML vs the product spec, evaluates marketing quality, and leaves direct inline review comments on GitHub PRs. Passes a verdict back to the CEO to trigger final revisions or deployment.

## 🔌 Core API Integrations
- **Groq API**: High-speed LLM orchestration using `llama-3.3-70b-versatile`.
- **GitHub REST API**: Branch initialization, programmatic commits, issue creation, PRs, and PR discussions.
- **Slack API**: Feature-rich broadcast messaging and actionable links using Block Kit UI.
- **SendGrid API**: Marketing cold email automation and outreach.

---

## 🚀 Setting Up

1. **Install dependencies:**
   LaunchMind requires `groq`, `python-dotenv`, `requests`, and `sendgrid`.
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure your Environment:**
   Copy the provided `.env.example` to `.env` and fill in your API credentials:
   ```bash
   cp .env.example .env
   ```
   **Required Keys:**
   - `GROQ_API_KEY`: Found at console.groq.com
   - `GITHUB_TOKEN`: A Github PAT with repo permissions
   - `GITHUB_REPO`: Your repository in `username/repo` format
   - `SLACK_BOT_TOKEN`: An OAuth Slack bot token (`xoxb-...`)
   - `SENDGRID_API_KEY`: Your SendGrid API key

3. **Run the system:**
   ```bash
   python main.py
   ```

Watch as the CEO Agent delegates tasks, the agents autonomously fulfill them, loops are created when code/copy quality dips, and your startup springs to life right in your terminal, GitHub, and Slack!
