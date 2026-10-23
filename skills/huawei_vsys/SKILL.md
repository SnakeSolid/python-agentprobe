---
name: huawei_vsys
description: How to create and configure a virtual system (vsys) on VRPv8.
---

# Creating a vsys

1. Enter system view: `system-view`
2. Create the vsys: `vsys name <name>`
3. Allocate resources: `assign interface <if>`
4. Commit: `engine configuration commit`

**Note:** The `commit` command is forbidden inside `syntax_check`; use it only
as the final step of a live configuration workflow.
