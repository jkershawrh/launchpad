"""Named workload profiles for performance demos."""

SCENARIO_PROMPTS = {
    "incident_storm": {
        "classification": [
            "Alert: Pod ocp-worker-03 CrashLoopBackOff in namespace gaudi-inference. 5 restarts in 2 minutes.",
            "Alert: Disk pressure on node ocp-virt8-host7. /var at 94% capacity. Eviction threshold approaching.",
            "Alert: SSL certificate for model-serving route expires in 18 hours.",
            "Alert: Unauthorized API access attempt from 10.130.2.55 — 403 on /v1/route 12 times in 60s.",
            "Alert: Memory utilization on gateway pod exceeded 85%. Current: 3.4Gi of 4Gi limit.",
            "Alert: LiteLLM proxy returned 5 consecutive 502 errors for codellama-7b-instruct model.",
            "Alert: Prometheus scrape target down — ServiceMonitor intel-rh-demo/gateway unreachable.",
        ],
        "embedding": [
            "Index this incident for semantic search: Production inference gateway latency spike during peak traffic window.",
            "Vectorize alert corpus: 47 alerts received in the last 15 minutes across 3 namespaces.",
            "Generate embedding for: 'Gaudi accelerator HBM utilization reached 97% causing inference queue backup.'",
        ],
        "rerank": [
            "Rerank these 8 runbook entries against the query: 'pod CrashLoopBackOff with OOMKilled exit code'",
            "Score relevance of 5 past incidents to current alert: 'inference gateway p99 latency > 10 seconds'",
        ],
        "short_summary": [
            "Summarize the last 30 minutes of alerts: 12 pod restarts, 3 node pressure warnings, 1 certificate expiry.",
            "Create executive brief: Production AI platform experienced cascading failures starting at 14:23 UTC.",
        ],
        "long_summary": [
            "Generate comprehensive incident timeline: From initial Gaudi memory pressure alert through full platform degradation, failover to Xeon 6, and recovery. Include all 47 alerts, operator actions, and automated responses.",
        ],
        "incident_rca": [
            "Root cause analysis: The Gaudi accelerator lane went offline at 14:23 UTC. 142 requests experienced SLA violations. Investigate the chain from batch_summary job consuming all HBM through cascade to gateway timeout.",
            "Deep analysis: Why did the fallback from Gaudi to Xeon 6 Performance lane take 4 minutes instead of the expected 30 seconds? Examine routing matrix evaluation, health check intervals, and connection pool state.",
        ],
        "batch_summary": [
            "Generate overnight operations report: 24-hour window covering 15,847 inference requests across 3 hardware tiers. Include route distribution, cost analysis, SLA compliance, and capacity planning recommendations.",
        ],
    },
    "rag_barrage": {
        "embedding": [
            "Embed this knowledge base article: How to configure Intel Gaudi device plugin on OpenShift 4.15+",
            "Vectorize: Red Hat OpenShift AI operator installation and KServe ServingRuntime configuration guide",
            "Generate embeddings for: 'Troubleshooting vLLM inference timeout errors on Xeon 6 with AMX optimization'",
            "Index document: Intel Gaudi2 HBM bandwidth specifications and workload sizing guidelines",
        ],
        "rerank": [
            "Rerank 10 documentation pages against: 'How to optimize model serving latency on Intel hardware'",
            "Score relevance of 6 KB articles for: 'Gaudi out of memory error during batch inference with 17B model'",
            "Cross-encoder rerank: Query='OpenShift route timeout configuration' against 8 candidate docs",
        ],
        "rag_question": [
            "Using the retrieved context, answer: What is the maximum model size that can run on a single Gaudi card without model parallelism?",
            "Based on the documentation, explain: How does the routing engine decide between Xeon 6 and Gaudi for a completion request?",
            "Answer from knowledge base: What are the recommended resource limits for a vLLM CPU inference pod on Xeon 6?",
            "RAG synthesis: Compare the throughput characteristics of Granite-tiny on Xeon 6 vs Llama-Scout-17B on Gaudi for classification tasks.",
        ],
        "document_summary": [
            "Summarize this 40-page deployment guide: Intel-Red Hat AI Inference Platform — covering architecture, hardware requirements, operator installation, model serving configuration, monitoring setup, and capacity planning.",
        ],
    },
    "token_cannon": {
        "long_summary": [
            "Generate detailed analysis of Intel Xeon 6 with AMX acceleration performance characteristics for AI inference workloads including classification, embeddings, reranking, and small model completion.",
            "Comprehensive comparison: vLLM serving on Intel Gaudi vs CPU-only deployment — covering throughput, latency, cost, power efficiency, and workload suitability across model sizes from 1B to 70B parameters.",
        ],
        "batch_summary": [
            "Weekly platform report: Aggregate 7 days of inference telemetry — 112,438 total requests, route distribution trends, cost accumulation by hardware tier, latency regression analysis, and capacity forecast.",
        ],
        "document_summary": [
            "Distill the complete Intel Gaudi2 architecture whitepaper: tensor engine specifications, HBM2E bandwidth, inter-die connectivity, software stack integration with PyTorch and vLLM, and performance benchmarks across LLM sizes.",
        ],
        "code_summary": [
            "Analyze the inference gateway codebase: router.py (routing logic), overdrive engine (lane evaluation), rubric system (check framework), database persistence, and API surface. Identify performance bottlenecks and optimization opportunities.",
            "Review and summarize the Kubernetes manifest architecture: Kustomize overlays, KServe ServingRuntime definitions, network policies, HPA configuration, and security context constraints.",
        ],
    },
    "model_race": {
        "classification": [
            "Classify: 'The GPU node is reporting thermal throttling above 85°C during sustained batch inference.'",
            "Categorize this support ticket: 'Model download fails with 403 from HuggingFace Hub behind corporate proxy.'",
        ],
        "short_summary": [
            "Quick summary: 3 alerts fired — pod restart on worker-03, high latency on gateway, certificate expiry warning.",
            "Brief: Current platform status across 3 inference lanes — eco healthy, performance at 78% utilization, overdrive idle.",
        ],
        "long_summary": [
            "Detailed performance comparison: Run identical classification, summarization, and generation tasks on Xeon 6 (eco lane) vs Xeon 6 (performance lane) vs Gaudi (overdrive lane). Report latency, throughput, and cost per token for each.",
        ],
        "document_summary": [
            "Summarize the platform architecture document covering dual-path inference routing across Intel Xeon 6 and Gaudi hardware, including the Overdrive lane evaluation engine, rubric-based decision framework, and failover mechanisms.",
        ],
    },
}

SCENARIO_NARRATIVES = {
    "incident_storm": {
        "title": "Enterprise Incident Storm",
        "story": "A production AI platform is under pressure. Alerts are flooding in — pod crashes, memory pressure, certificate expiry, and Gaudi accelerator overload. The platform must triage every alert (Xeon 6), find relevant runbooks (Xeon 6), generate root cause analysis (Gaudi), and produce executive summaries — all simultaneously.",
        "phases": [
            {"name": "Alert Triage", "tasks": ["classification"], "hw": "Xeon 6", "desc": "Incoming alerts are classified by severity and type on Xeon 6 — fast, cheap, no GPU needed."},
            {"name": "Knowledge Retrieval", "tasks": ["embedding", "rerank"], "hw": "Xeon 6", "desc": "Alert text is embedded and matched against runbooks using Xeon 6 with AMX acceleration."},
            {"name": "Situation Summary", "tasks": ["short_summary"], "hw": "Xeon 6", "desc": "Quick executive briefs are generated on Xeon 6 for the operations dashboard."},
            {"name": "Deep Analysis", "tasks": ["long_summary", "incident_rca"], "hw": "Gaudi", "desc": "Complex root cause analysis and detailed timelines are generated on Gaudi — these need the memory bandwidth and throughput for large context windows."},
            {"name": "Overnight Report", "tasks": ["batch_summary"], "hw": "Gaudi", "desc": "End-of-shift batch reports aggregate all incidents and generate capacity planning recommendations on Gaudi."},
        ],
    },
    "rag_barrage": {
        "title": "High-Throughput RAG Pipeline",
        "story": "An enterprise knowledge base is being queried at scale. Engineers are asking questions about Intel hardware configuration, OpenShift deployment, and model optimization. Every question triggers an embed-search-rerank-generate pipeline that spans both Xeon 6 and Gaudi.",
        "phases": [
            {"name": "Document Indexing", "tasks": ["embedding"], "hw": "Xeon 6", "desc": "Knowledge base articles are vectorized on Xeon 6 using nomic-embed for fast, parallel indexing."},
            {"name": "Relevance Scoring", "tasks": ["rerank"], "hw": "Xeon 6", "desc": "Retrieved documents are re-ranked by relevance using CodeLlama cross-encoder on Xeon 6."},
            {"name": "Answer Generation", "tasks": ["rag_question"], "hw": "Mixed", "desc": "Simple questions answered on Xeon 6. Complex multi-document synthesis routed to Gaudi for deeper reasoning."},
            {"name": "Document Distillation", "tasks": ["document_summary"], "hw": "Gaudi", "desc": "Long technical documents are condensed into actionable summaries on Gaudi's high-bandwidth memory."},
        ],
    },
    "token_cannon": {
        "title": "Maximum Generation Throughput",
        "story": "The platform is stress-tested with the heaviest generation workloads — long analyses, batch reports, document distillation, and codebase reviews. Nearly everything routes to Gaudi because these tasks demand large context windows and sustained token generation.",
        "phases": [
            {"name": "Long Analysis", "tasks": ["long_summary"], "hw": "Gaudi", "desc": "Multi-page technical analyses generated on Gaudi at 100+ tokens/sec."},
            {"name": "Batch Reports", "tasks": ["batch_summary"], "hw": "Gaudi", "desc": "Week-long telemetry aggregated into comprehensive reports on Gaudi's HBM."},
            {"name": "Document Distillation", "tasks": ["document_summary"], "hw": "Gaudi", "desc": "40+ page whitepapers condensed on Gaudi using the full 400K token context window."},
            {"name": "Code Review", "tasks": ["code_summary"], "hw": "Gaudi", "desc": "Codebase analysis and optimization recommendations generated on Gaudi."},
        ],
    },
    "model_race": {
        "title": "Cross-Hardware Performance Comparison",
        "story": "The same types of tasks are run across all three hardware tiers to demonstrate why hardware-aware routing matters. Small tasks prove Xeon 6 is faster and cheaper. Large tasks prove Gaudi is essential for throughput.",
        "phases": [
            {"name": "Small Tasks → Eco", "tasks": ["classification"], "hw": "Xeon 6 Eco", "desc": "Quick classification on the lightweight Granite model — fast response, minimal cost."},
            {"name": "Mid Tasks → Performance", "tasks": ["short_summary"], "hw": "Xeon 6 Perf", "desc": "Summaries generated on CodeLlama 7B with AMX — good throughput without GPU cost."},
            {"name": "Large Tasks → Overdrive", "tasks": ["long_summary", "document_summary"], "hw": "Gaudi", "desc": "Heavy generation on Llama Scout 17B — only viable on Gaudi's HBM bandwidth."},
        ],
    },
}

PROFILES = {
    "incident_storm": {
        "description": "Simulate an enterprise incident flood — classification, triage, RCA, and batch reporting.",
        "expected_lane_bias": {"eco": "classification/triage", "overdrive": "RCA and long summaries"},
        "narrative": SCENARIO_NARRATIVES["incident_storm"],
        "prompts": SCENARIO_PROMPTS["incident_storm"],
        "task_mix": [
            {"task_type": "classification", "weight": 25, "token_range": [500, 3000], "priority": "normal"},
            {"task_type": "embedding", "weight": 15, "token_range": [1000, 6000], "priority": "normal"},
            {"task_type": "rerank", "weight": 10, "token_range": [2000, 6000], "priority": "normal"},
            {"task_type": "short_summary", "weight": 15, "token_range": [2000, 12000], "priority": "high"},
            {"task_type": "long_summary", "weight": 10, "token_range": [16000, 32000], "priority": "high"},
            {"task_type": "incident_rca", "weight": 15, "token_range": [20000, 40000], "priority": "critical"},
            {"task_type": "batch_summary", "weight": 10, "token_range": [32000, 50000], "priority": "critical"},
        ],
    },
    "rag_barrage": {
        "description": "Simulate high-throughput RAG — embed, search, rerank, answer generation.",
        "expected_lane_bias": {"performance": "retrieval-side inference", "overdrive": "answer generation"},
        "narrative": SCENARIO_NARRATIVES["rag_barrage"],
        "prompts": SCENARIO_PROMPTS["rag_barrage"],
        "task_mix": [
            {"task_type": "embedding", "weight": 30, "token_range": [500, 4000], "priority": "normal"},
            {"task_type": "rerank", "weight": 25, "token_range": [1000, 6000], "priority": "normal"},
            {"task_type": "rag_question", "weight": 25, "token_range": [2000, 20000], "priority": "high"},
            {"task_type": "document_summary", "weight": 20, "token_range": [16000, 40000], "priority": "high"},
        ],
    },
    "token_cannon": {
        "description": "Maximize generated-token simulation — heavy generation across all lanes.",
        "expected_lane_bias": {"overdrive": "most heavy requests"},
        "narrative": SCENARIO_NARRATIVES["token_cannon"],
        "prompts": SCENARIO_PROMPTS["token_cannon"],
        "task_mix": [
            {"task_type": "long_summary", "weight": 30, "token_range": [16000, 50000], "priority": "high"},
            {"task_type": "batch_summary", "weight": 25, "token_range": [32000, 60000], "priority": "critical"},
            {"task_type": "document_summary", "weight": 25, "token_range": [20000, 45000], "priority": "high"},
            {"task_type": "code_summary", "weight": 20, "token_range": [16000, 40000], "priority": "high"},
        ],
    },
    "model_race": {
        "description": "Run comparable workloads across all lanes for cross-hardware comparison.",
        "expected_lane_bias": {"eco": "small tasks", "performance": "mid tasks", "overdrive": "large tasks"},
        "narrative": SCENARIO_NARRATIVES["model_race"],
        "prompts": SCENARIO_PROMPTS["model_race"],
        "task_mix": [
            {"task_type": "classification", "weight": 25, "token_range": [500, 3000], "priority": "normal"},
            {"task_type": "short_summary", "weight": 25, "token_range": [2000, 12000], "priority": "normal"},
            {"task_type": "long_summary", "weight": 25, "token_range": [16000, 32000], "priority": "high"},
            {"task_type": "document_summary", "weight": 25, "token_range": [20000, 40000], "priority": "high"},
        ],
    },
    "dashboard_storm": {
        "description": "Simulate operational dashboard screenshots flooding in — classify, summarize, interpret charts.",
        "expected_lane_bias": {"eco": "screenshot classification", "overdrive": "summary and chart interpretation"},
        "narrative": {"title": "Dashboard Storm", "story": "Operational dashboards are flooding the platform with screenshots. Xeon 6 classifies and sorts them instantly. Gaudi explains the high-value screenshots that need attention.", "phases": []},
        "prompts": {
            "screenshot_classification": ["Classify this Grafana dashboard screenshot: is it showing normal operations or an anomaly?", "Identify the type of operational dashboard: latency, throughput, error rate, or resource utilization."],
            "screenshot_summary": ["Summarize the operational issue visible in this Grafana dashboard showing a latency spike and elevated error rate.", "Explain what this Prometheus dashboard is showing about CPU utilization across the inference worker nodes."],
            "chart_interpretation": ["Interpret this time-series chart showing p99 latency increasing from 200ms to 4,500ms over 15 minutes.", "What does this throughput chart indicate about the relationship between request volume and Gaudi utilization?"],
            "multimodal_incident_summary": ["Synthesize these 5 dashboard screenshots into a single incident summary covering latency, error rate, and resource utilization trends."],
        },
        "task_mix": [
            {"task_type": "screenshot_classification", "weight": 30, "token_range": [500, 3000], "priority": "normal", "modality": "screenshot", "image_count_range": [1, 1]},
            {"task_type": "screenshot_summary", "weight": 25, "token_range": [8000, 20000], "priority": "high", "modality": "screenshot", "image_count_range": [1, 1]},
            {"task_type": "chart_interpretation", "weight": 25, "token_range": [8000, 18000], "priority": "high", "modality": "screenshot", "image_count_range": [1, 2]},
            {"task_type": "multimodal_incident_summary", "weight": 20, "token_range": [20000, 40000], "priority": "critical", "modality": "mixed", "image_count_range": [3, 5]},
        ],
    },
    "multimodal_incident_commander": {
        "description": "Incident triage using screenshots, logs, and metrics — classify, summarize, RCA.",
        "expected_lane_bias": {"eco": "classification", "overdrive": "incident synthesis and RCA"},
        "narrative": {"title": "Multimodal Incident Commander", "story": "A production incident is unfolding. Screenshots, log snippets, and metrics are pouring in. Xeon 6 handles fast classification. Gaudi synthesizes everything into root cause analysis.", "phases": []},
        "prompts": {
            "screenshot_summary": ["Summarize the Grafana dashboard showing inference gateway latency spike during peak traffic."],
            "chart_interpretation": ["Interpret this error rate chart showing 502 errors correlating with Gaudi memory pressure."],
            "multimodal_rca": ["Analyze these 3 dashboard screenshots and log excerpts to determine the root cause of the inference gateway timeout cascade."],
            "multimodal_incident_summary": ["Generate a comprehensive incident report combining dashboard screenshots, metrics, and alert timeline."],
            "document_visual_summary": ["Summarize this 10-page incident post-mortem document with embedded charts and architecture diagrams."],
        },
        "task_mix": [
            {"task_type": "screenshot_summary", "weight": 20, "token_range": [8000, 18000], "priority": "high", "modality": "screenshot", "image_count_range": [1, 1]},
            {"task_type": "chart_interpretation", "weight": 15, "token_range": [8000, 16000], "priority": "high", "modality": "screenshot", "image_count_range": [1, 2]},
            {"task_type": "multimodal_rca", "weight": 25, "token_range": [20000, 40000], "priority": "critical", "modality": "mixed", "image_count_range": [2, 4]},
            {"task_type": "multimodal_incident_summary", "weight": 20, "token_range": [20000, 35000], "priority": "critical", "modality": "mixed", "image_count_range": [3, 6]},
            {"task_type": "document_visual_summary", "weight": 20, "token_range": [16000, 30000], "priority": "high", "modality": "document", "page_count_range": [5, 15]},
        ],
    },
    "architecture_explainer": {
        "description": "Feed architecture diagrams and ask for technical explanations.",
        "expected_lane_bias": {"overdrive": "diagram explanations and visual RAG"},
        "narrative": {"title": "Architecture Explainer", "story": "Architecture diagrams are submitted for AI-powered explanation. Gaudi handles the heavy vision-language reasoning to interpret complex system diagrams.", "phases": []},
        "prompts": {
            "diagram_explanation": ["Explain this architecture diagram showing the dual-path inference routing across Xeon 6 and Gaudi hardware.", "Describe the data flow shown in this Kubernetes deployment diagram with KServe ServingRuntimes."],
            "visual_rag_question": ["Looking at this architecture diagram, explain how the routing engine decides between Xeon 6 and Gaudi for each request.", "Based on this deployment diagram, what happens when the Gaudi accelerator node goes offline?"],
            "document_visual_summary": ["Summarize this technical architecture document with embedded diagrams covering the Intel-Red Hat inference platform."],
        },
        "task_mix": [
            {"task_type": "diagram_explanation", "weight": 40, "token_range": [10000, 25000], "priority": "high", "modality": "diagram", "image_count_range": [1, 1]},
            {"task_type": "visual_rag_question", "weight": 35, "token_range": [12000, 22000], "priority": "high", "modality": "mixed", "image_count_range": [1, 2]},
            {"task_type": "document_visual_summary", "weight": 25, "token_range": [16000, 35000], "priority": "high", "modality": "document", "page_count_range": [5, 20]},
        ],
    },
    "visual_rag_barrage": {
        "description": "Multimodal RAG — embed images, search visually, extract text, answer questions.",
        "expected_lane_bias": {"performance": "retrieval-side multimodal", "overdrive": "answer generation"},
        "narrative": {"title": "Visual RAG Barrage", "story": "A multimodal knowledge base is queried at scale. Documents with images, diagrams, and screenshots are indexed, searched, and answered — spanning Xeon 6 for retrieval and Gaudi for synthesis.", "phases": []},
        "prompts": {
            "image_text_embedding": ["Embed this diagram and its caption for semantic search: Intel Gaudi accelerator architecture.", "Vectorize this screenshot and surrounding text for multimodal retrieval."],
            "visual_similarity": ["Find screenshots visually similar to this Grafana latency dashboard.", "Search for diagrams that look similar to this inference routing architecture."],
            "ocr_layout_extract": ["Extract text and layout from this scanned architecture document page.", "OCR this screenshot to extract metric values and panel labels."],
            "visual_rag_question": ["Using the retrieved documents and screenshots, explain the inference routing decision flow.", "Based on these architecture diagrams and docs, how does failover work between Xeon 6 and Gaudi?"],
            "document_visual_summary": ["Summarize this multi-page technical document with embedded charts and architecture diagrams."],
        },
        "task_mix": [
            {"task_type": "image_text_embedding", "weight": 25, "token_range": [500, 4000], "priority": "normal", "modality": "image", "image_count_range": [1, 1]},
            {"task_type": "visual_similarity", "weight": 20, "token_range": [1000, 6000], "priority": "normal", "modality": "image", "image_count_range": [1, 1]},
            {"task_type": "ocr_layout_extract", "weight": 15, "token_range": [2000, 6000], "priority": "normal", "modality": "document", "page_count_range": [1, 3]},
            {"task_type": "visual_rag_question", "weight": 25, "token_range": [10000, 22000], "priority": "high", "modality": "mixed", "image_count_range": [1, 3]},
            {"task_type": "document_visual_summary", "weight": 15, "token_range": [16000, 35000], "priority": "high", "modality": "document", "page_count_range": [5, 15]},
        ],
    },
    "token_cannon_multimodal": {
        "description": "Stress heavy multimodal generation — screenshots, charts, documents, RCA.",
        "expected_lane_bias": {"overdrive": "most heavy multimodal requests"},
        "narrative": {"title": "Token Cannon: Multimodal", "story": "Maximum multimodal generation throughput. Nearly everything routes to Gaudi because these tasks demand vision-language reasoning with large context windows.", "phases": []},
        "prompts": {
            "screenshot_summary": ["Generate a detailed analysis of this operations dashboard showing multi-service degradation across 6 panels."],
            "chart_interpretation": ["Provide an in-depth interpretation of this complex multi-axis chart showing throughput, latency, and error rate correlations over 24 hours."],
            "document_visual_summary": ["Distill this 30-page architecture whitepaper with 15 embedded diagrams into a comprehensive technical summary."],
            "multimodal_rca": ["Deep root cause analysis using 8 dashboard screenshots, 3 architecture diagrams, and 50 log lines from the inference gateway incident."],
        },
        "task_mix": [
            {"task_type": "screenshot_summary", "weight": 25, "token_range": [10000, 25000], "priority": "high", "modality": "screenshot", "image_count_range": [1, 3]},
            {"task_type": "chart_interpretation", "weight": 20, "token_range": [10000, 22000], "priority": "high", "modality": "screenshot", "image_count_range": [1, 2]},
            {"task_type": "document_visual_summary", "weight": 30, "token_range": [20000, 45000], "priority": "high", "modality": "document", "page_count_range": [10, 30]},
            {"task_type": "multimodal_rca", "weight": 25, "token_range": [25000, 50000], "priority": "critical", "modality": "mixed", "image_count_range": [4, 8]},
        ],
    },
    "image_to_manual": {
        "description": "Generate technical manuals and documentation from product/equipment images.",
        "expected_lane_bias": {"eco": "image classification", "overdrive": "manual generation"},
        "narrative": {"title": "Image to Manual", "story": "Product images and equipment photos are submitted. The platform identifies what it's looking at, then generates installation guides, operating manuals, and troubleshooting docs — all from a single image.", "phases": []},
        "prompts": {
            "image_classification": ["Identify this hardware component: is it a server, accelerator card, network switch, or storage device?", "Classify this equipment image: rack-mounted, blade, tower, or standalone appliance."],
            "image_to_manual": [
                "Generate a complete installation manual for the Intel Gaudi accelerator card shown in this image. Include safety precautions, hardware requirements, step-by-step installation, verification commands, and troubleshooting.",
                "Create a quick-start guide for this 2U rack server. Include what's in the box, rack installation steps, first boot procedure, and OpenShift node setup instructions.",
                "Write a hardware maintenance guide for this server based on the image. Include component identification, replacement procedures, LED indicator meanings, and preventive maintenance schedule.",
                "Generate an operator's manual for this network switch shown in the image. Include port layout, initial configuration, VLAN setup, and monitoring commands.",
            ],
            "screenshot_summary": ["Describe the hardware configuration visible in this server management interface screenshot."],
            "document_visual_summary": ["Summarize this hardware installation guide with embedded photos showing component placement and cable routing."],
        },
        "task_mix": [
            {"task_type": "image_classification", "weight": 20, "token_range": [500, 2000], "priority": "normal", "modality": "image", "image_count_range": [1, 1]},
            {"task_type": "image_to_manual", "weight": 50, "token_range": [10000, 35000], "priority": "high", "modality": "image", "image_count_range": [1, 3]},
            {"task_type": "screenshot_summary", "weight": 15, "token_range": [8000, 16000], "priority": "high", "modality": "screenshot", "image_count_range": [1, 1]},
            {"task_type": "document_visual_summary", "weight": 15, "token_range": [16000, 30000], "priority": "high", "modality": "document", "page_count_range": [5, 20]},
        ],
    },
}


def list_profiles() -> list[dict]:
    return [{"name": name, "description": p["description"]} for name, p in PROFILES.items()]
