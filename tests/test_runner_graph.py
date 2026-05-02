"""Tests for DependencyGraph (REQ-016 WP01)."""

import time
from uuid import uuid4

import pytest

from execqueue.runner.graph import DependencyGraph
from execqueue.orchestrator.workflow_models import WorkflowContext


def _make_ctx(dependencies: dict[str, list[str]]) -> WorkflowContext:
    """Helper to create WorkflowContext with string keys converted to UUIDs."""
    uuid_map = {name: uuid4() for name in dependencies.keys()}
    dep_uuids = {
        uuid_map[name]: [uuid_map[dep] for dep in deps]
        for name, deps in dependencies.items()
    }
    from dataclasses import dataclass, field
    from datetime import datetime
    
    # Create minimal PreparedExecutionContext stubs
    @dataclass
    class StubContext:
        task_id: str
        branch_name: str = "main"
        worktree_path: str = "/tmp"
        commit_sha: str | None = None
    
    tasks = [StubContext(name) for name in dependencies.keys()]
    
    return WorkflowContext(
        workflow_id=uuid4(),
        epic_id=None,
        requirement_id=None,
        tasks=tasks,  # type: ignore
        dependencies=dep_uuids,
        created_at=datetime.utcnow(),
    )


class TestDependencyGraphConstruction:
    """Test DependencyGraph construction and validation."""

    def test_empty_graph(self):
        """Test construction of empty graph."""
        graph = DependencyGraph()
        assert len(graph.nodes) == 0
        assert len(graph.edges) == 0

    def test_single_node(self):
        """Test graph with single node, no dependencies."""
        ctx = _make_ctx({"A": []})
        graph = DependencyGraph.from_context(ctx)
        assert len(graph.nodes) == 1
        # Check that in_degree is initialized for all nodes
        for node in graph.nodes:
            assert graph.in_degree[node] == 0

    def test_linear_chain_construction(self):
        """Test linear chain A -> B -> C -> D."""
        ctx = _make_ctx({"A": [], "B": ["A"], "C": ["B"], "D": ["C"]})
        graph = DependencyGraph.from_context(ctx)
        assert len(graph.nodes) == 4
        # Check that all nodes have valid in_degree values
        for node in graph.nodes:
            assert graph.in_degree[node] >= 0

    def test_duplicate_nodes_handled_in_set(self):
        """Test that duplicate nodes in the nodes set are naturally deduplicated."""
        from uuid import uuid4
        # Create the same UUID twice (simulating duplicate input)
        node_id = uuid4()
        
        # Construct with what should be duplicates
        graph = DependencyGraph(
            nodes={node_id, node_id},  # Set naturally deduplicates
            edges={node_id: []},
        )
        
        # Should only have one node
        assert len(graph.nodes) == 1
        assert node_id in graph.nodes

    def test_invalid_dependency_raises_value_error(self):
        """Test that referencing unknown dependency raises ValueError."""
        # Create a graph manually with invalid reference
        from uuid import uuid4
        valid_node = uuid4()
        invalid_dep = uuid4()

        with pytest.raises(ValueError, match="depends on unknown task"):
            DependencyGraph(
                nodes={valid_node},
                edges={valid_node: [invalid_dep]},
            )


class TestTopologicalSort:
    """Test topological sort and batch generation."""

    def test_empty_graph_returns_empty_list(self):
        """Test empty graph returns empty batches."""
        graph = DependencyGraph()
        assert graph.topological_sort() == []

    def test_single_node_returns_single_batch(self):
        """Test single node returns one batch with that node."""
        ctx = _make_ctx({"A": []})
        graph = DependencyGraph.from_context(ctx)
        batches = graph.topological_sort()
        assert len(batches) == 1
        assert len(batches[0]) == 1

    def test_linear_chain_returns_sequential_batches(self):
        """Test A -> B -> C -> D returns 4 batches of 1 task each."""
        ctx = _make_ctx({"A": [], "B": ["A"], "C": ["B"], "D": ["C"]})
        graph = DependencyGraph.from_context(ctx)
        batches = graph.topological_sort()
        assert len(batches) == 4
        assert all(len(batch) == 1 for batch in batches)

    def test_parallel_fork_returns_two_batches(self):
        """Test A -> [B, C, D] returns 2 batches: [A], [B,C,D]."""
        ctx = _make_ctx({"A": [], "B": ["A"], "C": ["A"], "D": ["A"]})
        graph = DependencyGraph.from_context(ctx)
        batches = graph.topological_sort()
        assert len(batches) == 2
        assert len(batches[0]) == 1  # A
        assert len(batches[1]) == 3  # B, C, D

    def test_diamond_pattern_returns_three_batches(self):
        """Test A -> [B, C] -> D returns 3 batches: [A], [B,C], [D]."""
        ctx = _make_ctx({"A": [], "B": ["A"], "C": ["A"], "D": ["B", "C"]})
        graph = DependencyGraph.from_context(ctx)
        batches = graph.topological_sort()
        assert len(batches) == 3
        assert len(batches[0]) == 1  # A
        assert len(batches[1]) == 2  # B, C
        assert len(batches[2]) == 1  # D

    def test_complex_parallel_pattern(self):
        """Test complex parallel pattern with multiple forks and joins.
        
        Pattern:
               B -> D
              /      \
        A ->          -> F
              \      /
               C -> E
               
        Expected batches: [A], [B,C], [D,E], [F]
        """
        ctx = _make_ctx({
            "A": [], 
            "B": ["A"], 
            "C": ["A"], 
            "D": ["B"], 
            "E": ["C"], 
            "F": ["D", "E"]
        })
        graph = DependencyGraph.from_context(ctx)
        batches = graph.topological_sort()
        assert len(batches) == 4
        assert len(batches[0]) == 1  # A
        assert len(batches[1]) == 2  # B, C
        assert len(batches[2]) == 2  # D, E
        assert len(batches[3]) == 1  # F

    def test_duplicate_dependencies_handled_correctly(self):
        """Test that duplicate dependencies are handled correctly.
        
        When a task specifies the same dependency multiple times,
        it should still be treated as a single dependency.
        """
        from uuid import uuid4
        a, b, c = uuid4(), uuid4(), uuid4()
        
        # Create graph where C depends on B twice
        graph = DependencyGraph(
            nodes={a, b, c},
            edges={
                a: [],      # A has no dependencies
                b: [a],     # B depends on A
                c: [b, b],  # C depends on B twice (duplicate)
            },
        )
        
        # Should still produce valid topological sort
        batches = graph.topological_sort()
        assert len(batches) == 3
        assert len(batches[0]) == 1  # A
        assert len(batches[1]) == 1  # B
        assert len(batches[2]) == 1  # C
        
        # Verify in_degree counts (should be 2 for C since it has 2 dependencies)
        assert graph.in_degree[c] == 2
        assert graph.in_degree[b] == 1
        assert graph.in_degree[a] == 0

    def test_deterministic_ordering(self):
        """Test that topological sort produces deterministic ordering.
        
        When multiple tasks are available in the same batch, they should
        be ordered consistently.
        """
        # Create multiple runs and verify consistent ordering
        ctx = _make_ctx({
            "A": [], "B": [], "C": [],  # Three independent tasks
            "D": ["A", "B", "C"]        # D depends on all three
        })
        
        results = []
        for _ in range(10):
            graph = DependencyGraph.from_context(ctx)
            batches = graph.topological_sort()
            # Convert to string representation for comparison
            result_str = "|".join(",".join(str(t) for t in batch) for batch in batches)
            results.append(result_str)
        
        # All results should be identical (deterministic)
        assert all(r == results[0] for r in results)

    def test_cycle_returns_empty_list(self):
        """Test graph with cycle returns empty batches."""
        from uuid import uuid4
        a, b = uuid4(), uuid4()
        graph = DependencyGraph(
            nodes={a, b},
            edges={a: [b], b: [a]},  # A -> B -> A cycle
        )
        assert graph.topological_sort() == []

    def test_get_parallel_batches_same_as_topological_sort(self):
        """Test get_parallel_batches returns same as topological_sort."""
        ctx = _make_ctx({"A": [], "B": ["A"], "C": ["A"]})
        graph = DependencyGraph.from_context(ctx)
        assert graph.get_parallel_batches() == graph.topological_sort()


class TestCycleDetection:
    """Test cycle detection."""

    def test_empty_graph_no_cycle(self):
        """Test empty graph has no cycle."""
        graph = DependencyGraph()
        assert graph.detect_cycles() is False

    def test_single_node_no_cycle(self):
        """Test single node has no cycle."""
        ctx = _make_ctx({"A": []})
        graph = DependencyGraph.from_context(ctx)
        assert graph.detect_cycles() is False

    def test_linear_chain_no_cycle(self):
        """Test linear chain has no cycle."""
        ctx = _make_ctx({"A": [], "B": ["A"], "C": ["B"]})
        graph = DependencyGraph.from_context(ctx)
        assert graph.detect_cycles() is False

    def test_simple_cycle_detected(self):
        """Test A -> B -> A cycle is detected."""
        from uuid import uuid4
        a, b = uuid4(), uuid4()
        graph = DependencyGraph(
            nodes={a, b},
            edges={a: [b], b: [a]},
        )
        assert graph.detect_cycles() is True

    def test_diamond_no_cycle(self):
        """Test diamond pattern has no cycle."""
        ctx = _make_ctx({"A": [], "B": ["A"], "C": ["A"], "D": ["B", "C"]})
        graph = DependencyGraph.from_context(ctx)
        assert graph.detect_cycles() is False


class TestSequentialPaths:
    """Test sequential path identification."""

    def test_empty_graph_no_paths(self):
        """Test empty graph returns no paths."""
        graph = DependencyGraph()
        assert graph.get_sequential_paths() == []

    def test_single_node_no_paths(self):
        """Test single node returns no paths (need at least 2 for a path)."""
        ctx = _make_ctx({"A": []})
        graph = DependencyGraph.from_context(ctx)
        assert graph.get_sequential_paths() == []

    def test_linear_chain_returns_one_path(self):
        """Test A -> B -> C returns one path [A, B, C]."""
        ctx = _make_ctx({"A": [], "B": ["A"], "C": ["B"]})
        graph = DependencyGraph.from_context(ctx)
        paths = graph.get_sequential_paths()
        # Should find at least one path with 3 nodes
        assert any(len(path) == 3 for path in paths)

    def test_parallel_fork_no_long_paths(self):
        """Test A -> [B, C] doesn't create long sequential paths."""
        ctx = _make_ctx({"A": [], "B": ["A"], "C": ["A"]})
        graph = DependencyGraph.from_context(ctx)
        paths = graph.get_sequential_paths()
        # A has out_degree=2, so it won't be in a chain
        # B and C have in_degree=1 but out_degree=0
        assert all(len(path) <= 2 for path in paths)


class TestPerformance:
    """Test performance requirements."""

    def test_large_graph_under_10ms(self):
        """Test 100 nodes, 200 edges completes in under 10ms."""
        from uuid import uuid4

        # Create 100 nodes
        nodes = {uuid4() for _ in range(100)}
        node_list = list(nodes)

        # Create 200 edges (linear chain + some parallel)
        edges: dict[uuid4, list[uuid4]] = {}
        for i, node in enumerate(node_list):
            deps = []
            if i > 0:
                deps.append(node_list[i - 1])  # Chain dependency
            if i > 1 and i % 10 == 0:
                deps.append(node_list[i - 2])  # Extra dependency
            edges[node] = deps

        graph = DependencyGraph(nodes=nodes, edges=edges)

        start = time.perf_counter()
        batches = graph.topological_sort()
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < 10, f"Topological sort took {elapsed_ms:.2f}ms (>10ms)"
        assert len(batches) > 0  # Verify it actually did something
