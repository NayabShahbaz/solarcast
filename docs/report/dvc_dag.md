```mermaid
flowchart TD
	node1["evaluate"]
	node2["ingest"]
	node3["preprocess"]
	node4["train_baseline"]
	node5["train_tft"]
	node6["validate"]
	node2-->node3
	node3-->node1
	node3-->node4
	node3-->node5
	node3-->node6
	node4-->node1
	node5-->node1
	node6-->node4
	node6-->node5
```
