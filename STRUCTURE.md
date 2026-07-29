```
government-agent-platform/

│
├── README.md
├── CLAUDE.md
├── pyproject.toml
├── docker-compose.yml
├── .env.example
│
│
├── docs/
│
│   ├── ARCHITECTURE.md
│   ├── AGENT_DESIGN.md
│   ├── LANGGRAPH_DESIGN.md
│   ├── MCP_DESIGN.md
│   ├── A2A_DESIGN.md
│   ├── EVALUATION.md
│   └── DEPLOYMENT.md
│
│
├── requirements/
│
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   ├── requirements-gpu.txt
│   └── requirements-prod.txt
│
│
├── backend/
│
│   ├── main.py
│   │
│   │
│   ├── api/
│   │
│   │   ├── routes/
│   │   │
│   │   ├── chat.py
│   │   ├── workflow.py
│   │   ├── callback.py
│   │   └── evaluation.py
│   │
│   │
│   │   └── middleware/
│   │
│   │       ├── auth.py
│   │       ├── guard.py
│   │       └── logging.py
│   │
│   │
│   ├── core/
│   │
│   │   ├── config.py
│   │   ├── logger.py
│   │   ├── exception.py
│   │   └── security.py
│   │
│   │
│   └── dependencies.py
│
│
├── agents/
│
│   ├── supervisor/
│   │
│   │   ├── agent.py
│   │   ├── planner.py
│   │   └── router.py
│   │
│   │
│   ├── intent/
│   │
│   │   ├── agent.py
│   │   ├── classifier.py
│   │   └── bert_model.py
│   │
│   │
│   ├── policy/
│   │
│   │   ├── agent.py
│   │   ├── retriever.py
│   │   └── prompt.py
│   │
│   │
│   ├── material/
│   │
│   │   ├── agent.py
│   │   ├── extractor.py
│   │   └── validator.py
│   │
│   │
│   ├── workflow/
│   │
│   │   ├── agent.py
│   │   └── executor.py
│   │
│   │
│   └── governance/
│
│       ├── agent.py
│       └── analyzer.py
│
│
├── orchestration/
│
│   └── langgraph/
│
│       ├── graph.py
│       ├── state.py
│       ├── nodes.py
│       ├── edges.py
│       └── checkpoint.py
│
│
├── runtime/
│
│   ├── executor.py
│   ├── scheduler.py
│   ├── limiter.py
│   ├── loop_detector.py
│   └── context.py
│
│
├── tools/
│
│   ├── mcp/
│   │
│   │   ├── client.py
│   │   ├── gateway.py
│   │   │
│   │   └── servers/
│   │
│   │       ├── policy/
│   │       │
│   │       ├── server.py
│   │       ├── tools.py
│   │       └── schema.py
│   │
│   │       ├── material/
│   │       └── workflow/
│   │
│   │
│   └── a2a/
│
│       ├── connector.py
│       ├── protocol.py
│       ├── callback.py
│       └── mock_agents/
│
│
├── rag/
│
│   ├── loader.py
│   ├── splitter.py
│   ├── embedding.py
│   ├── vector_store.py
│   ├── retriever.py
│   └── reranker.py
│
│
├── model/
│
│   ├── llm_client.py
│   ├── embedding_client.py
│   └── reranker_client.py
│
│
├── governance/
│
│   ├── trace/
│   │
│   │   ├── collector.py
│   │   ├── storage.py
│   │   └── schema.py
│   │
│   ├── guardrail/
│   │
│   │   ├── pii.py
│   │   ├── injection.py
│   │   └── output_filter.py
│   │
│   ├── prompt/
│   │
│   │   ├── registry.py
│   │   └── version.py
│   │
│   └── evaluation/
│
│       ├── evaluator.py
│       ├── metrics.py
│       ├── benchmark.py
│       └── cases/
│
│
├── database/
│
│   ├── models/
│   │
│   │   ├── trace.py
│   │   ├── agent.py
│   │   ├── prompt.py
│   │   └── evaluation.py
│   │
│   ├── postgres.py
│   ├── redis.py
│   └── migrations/
│
│
├── frontend/
│
│   └── dashboard/
│
│       ├── src/
│       │
│       ├── trace/
│       ├── evaluation/
│       └── agent/
│
│
├── tests/
│
│   ├── unit/
│   │
│   ├── integration/
│   │
│   ├── test_agent.py
│   ├── test_mcp.py
│   ├── test_a2a.py
│   └── test_evaluation.py
│
│
└── deploy/
    
    ├── Dockerfile
    ├── docker-compose.yml
    ├── nginx.conf
    └── k8s/

```