"""Dependency graph infrastructure for workflow execution (REQ-016)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from uuid import UUID

    from execqueue.orchestrator.workflow_models import WorkflowContext


@dataclass
class DependencyGraph:
    """Directed acyclic graph (DAG) of task dependencies.

    Internal representation:
        - nodes: All task IDs in the workflow
        - edges: Map of task_id -> [dependencies] (incoming edges / predecessors)
        - reverse_edges: Map of task_id -> [dependents] (outgoing edges / successors)
        - in_degree: Map of task_id -> number of incoming edges (dependencies)

    Usage:
        graph = DependencyGraph.from_context(workflow_context)
        batches = graph.get_parallel_batches()  # [[A], [B, C], [D]]
        paths = graph.get_sequential_paths()    # [[A, D], [B], [C]]
        has_cycle = graph.detect_cycles()       # False for valid workflows
    """

    nodes: set[UUID] = field(default_factory=set)
    edges: dict[UUID, list[UUID]] = field(default_factory=dict)
    reverse_edges: dict[UUID, list[UUID]] = field(default_factory=dict)
    in_degree: dict[UUID, int] = field(default_factory=dict)

    def __post_init__(self):
        """Initialize graph structures and validate dependencies.

        Performs:
        1. Initialize all nodes with default values
        2. Build reverse edges from forward edges
        3. Calculate in-degree for each node
        4. Validate that all dependencies exist as nodes
        """
        # Initialize all nodes with default values
        for task_id in self.nodes:
            self.in_degree.setdefault(task_id, 0)
            self.reverse_edges.setdefault(task_id, [])
            self.edges.setdefault(task_id, [])

        # Build reverse edges and calculate in-degree
        for task_id, dependencies in self.edges.items():
            for dep_id in dependencies:
                # Validate: all referenced dependencies must exist as nodes
                if dep_id not in self.nodes:
                    raise ValueError(
                        f"Task {task_id} depends on unknown task {dep_id}"
                    )

                # Build reverse edge: dep_id -> task_id (task_id depends on dep_id)
                if dep_id in self.reverse_edges:
                    self.reverse_edges[dep_id].append(task_id)

                # Increment in-degree: task_id has one more dependency
                self.in_degree[task_id] += 1

    @classmethod
    def from_context(cls, ctx: "WorkflowContext") -> "DependencyGraph":
        """Create DependencyGraph from WorkflowContext.

        Args:
            ctx: WorkflowContext with tasks and dependencies

        Returns:
            DependencyGraph built from context

        Example:
            ctx = WorkflowContext(workflow_id=..., tasks=[...], dependencies={...})
            graph = DependencyGraph.from_context(ctx)
        """
        nodes = set(ctx.dependencies.keys())
        edges = dict(ctx.dependencies)

        return cls(nodes=nodes, edges=edges)

    def topological_sort(self) -> list[list[UUID]]:
        """Perform topological sort using Kahn's algorithm.

        Returns:
            List of batches, where each batch contains tasks that can run in parallel.
            Returns empty list if cycle is detected.

        Complexity: O(V + E) time, O(V) space

        Example:
            A -> B -> C  =>  [[A], [B], [C]]
            A -> [B, C]  =>  [[A], [B, C]]
        """
        # Copy in-degree to avoid modifying original
        in_degree = dict(self.in_degree)
        batches = []

        # Find all nodes with no dependencies (in_degree = 0)
        # Sort for deterministic ordering
        queue = sorted([n for n in self.nodes if in_degree.get(n, 0) == 0])

        while queue:
            # Current batch: all nodes with in_degree = 0
            batches.append(list(queue))

            # Prepare next batch
            next_queue = []
            for node in queue:
                # For each dependent of this node
                for dependent in self.reverse_edges.get(node, []):
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        next_queue.append(dependent)

            # Sort for deterministic ordering
            queue = sorted(next_queue)

        # Check for cycle: if not all nodes processed, there's a cycle
        processed = sum(len(batch) for batch in batches)
        if processed != len(self.nodes):
            return []  # Cycle detected

        return batches

    def detect_cycles(self) -> bool:
        """Detect if the graph contains any cycles.

        Returns:
            True if cycle exists, False otherwise

        Complexity: O(V + E) time using DFS

        Note:
            Uses iterative DFS to avoid stack overflow on large graphs.
        """
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {node: WHITE for node in self.nodes}

        def dfs(node: UUID) -> bool:
            """Returns True if cycle detected."""
            color[node] = GRAY

            for dep in self.edges.get(node, []):
                if dep not in color:
                    continue
                if color[dep] == GRAY:
                    return True  # Back edge found => cycle
                if color[dep] == WHITE and dfs(dep):
                    return True

            color[node] = BLACK
            return False

        for node in self.nodes:
            if color[node] == WHITE:
                if dfs(node):
                    return True

        return False

    def get_sequential_paths(self) -> list[list[UUID]]:
        """Identify sequential chains in the graph.

        Returns:
            List of paths, where each path is a sequence of tasks with
            in_degree=1 and out_degree=1 (simple chains).

        Note:
            This is a best-effort identification. Complex graph topologies
            (e.g., diamond patterns) may not be fully captured.

        Example:
            A -> B -> C  =>  [[A, B, C]]
            A -> [B, C]  =>  [[A], [B], [C]]  (B and C are not in chains)
        """
        paths = []
        visited = set()

        # Find all chain starts: nodes with in_degree = 0 or > 1
        for node in sorted(self.nodes):
            if node in visited:
                continue

            in_deg = self.in_degree.get(node, 0)
            out_deg = len(self.reverse_edges.get(node, []))

            # Chain start: no dependencies or multiple dependencies
            if in_deg <= 1 and out_deg >= 1:
                path = [node]
                visited.add(node)
                current = node

                # Follow the chain
                while True:
                    successors = self.reverse_edges.get(current, [])
                    if len(successors) != 1:
                        break  # Not a simple chain

                    next_node = successors[0]
                    next_in_deg = self.in_degree.get(next_node, 0)

                    # Continue only if next node also has in_degree = 1
                    if next_in_deg != 1:
                        break

                    path.append(next_node)
                    visited.add(next_node)
                    current = next_node

                if len(path) > 1:
                    paths.append(path)

        return paths

    def get_parallel_batches(self) -> list[list[UUID]]:
        """Get parallel execution batches.

        Returns:
            Same as topological_sort(). Provided for semantic clarity.

        Example:
            [[A], [B, C], [D]] means:
            - Batch 0: Execute A
            - Batch 1: Execute B and C in parallel
            - Batch 2: Execute D
        """
        return self.topological_sort()
