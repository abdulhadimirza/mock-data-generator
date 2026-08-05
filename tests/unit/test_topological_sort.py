from shared.tools import get_topological_table_order


def test_linear_dependency_chain():
    schema = {
        "order_items": {
            "foreign_keys": [{"table": "orders", "from": "order_id", "to": "id"}]
        },
        "orders": {
            "foreign_keys": [{"table": "users", "from": "user_id", "to": "id"}]
        },
        "users": {
            "foreign_keys": [{"table": "roles", "from": "role_id", "to": "id"}]
        },
        "roles": {
            "foreign_keys": []
        }
    }
    order = get_topological_table_order(schema)
    assert order.index("roles") < order.index("users")
    assert order.index("users") < order.index("orders")
    assert order.index("orders") < order.index("order_items")


def test_multi_parent_dependency():
    schema = {
        "order_items": {
            "foreign_keys": [
                {"table": "orders", "from": "order_id", "to": "id"},
                {"table": "products", "from": "product_id", "to": "id"}
            ]
        },
        "orders": {
            "foreign_keys": [{"table": "users", "from": "user_id", "to": "id"}]
        },
        "products": {
            "foreign_keys": [{"table": "categories", "from": "category_id", "to": "id"}]
        },
        "users": {"foreign_keys": []},
        "categories": {"foreign_keys": []}
    }
    order = get_topological_table_order(schema)
    assert order.index("users") < order.index("orders")
    assert order.index("categories") < order.index("products")
    assert order.index("orders") < order.index("order_items")
    assert order.index("products") < order.index("order_items")


def test_self_referencing_foreign_key():
    schema = {
        "employees": {
            "foreign_keys": [
                {"table": "employees", "from": "manager_id", "to": "id"},
                {"table": "departments", "from": "dept_id", "to": "id"}
            ]
        },
        "departments": {
            "foreign_keys": []
        }
    }
    order = get_topological_table_order(schema)
    assert order.index("departments") < order.index("employees")
    assert len(order) == 2


def test_disconnected_tables():
    schema = {
        "table_c": {"foreign_keys": []},
        "table_a": {"foreign_keys": []},
        "table_b": {"foreign_keys": []}
    }
    order = get_topological_table_order(schema)
    assert set(order) == {"table_a", "table_b", "table_c"}
    assert len(order) == 3


def test_circular_dependency_fallback():
    schema = {
        "table_a": {"foreign_keys": [{"table": "table_b", "from": "b_id", "to": "id"}]},
        "table_b": {"foreign_keys": [{"table": "table_a", "from": "a_id", "to": "id"}]}
    }
    order = get_topological_table_order(schema)
    assert len(order) == 2
    assert "table_a" in order and "table_b" in order
