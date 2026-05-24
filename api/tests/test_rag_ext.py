"""Unit tests for new app.rag functions: index_products, delete_products_by_batch, _textualize_product, search with where."""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app import rag


@pytest.fixture(autouse=True)
def reset_rag_globals():
    rag.client._chroma_client = None
    yield
    rag.client._chroma_client = None


@pytest.fixture
def tenant_id() -> UUID:
    return uuid4()


@pytest.fixture
def mock_chroma():
    col = MagicMock(name="collection")
    col.count.return_value = 5
    col.name = "test_collection"

    client = MagicMock(name="chroma_client")
    client.get_or_create_collection.return_value = col

    with patch("app.rag.client._chroma", return_value=client):
        with patch.object(rag.client, "_chroma_client", client):
            yield col, client


@pytest.fixture
def mock_openai():
    mock_client = MagicMock(name="openai_client")
    fake_data = [MagicMock(embedding=[0.1, 0.2, 0.3])]
    mock_response = MagicMock()
    mock_response.data = fake_data
    mock_client.embeddings.create.return_value = mock_response

    with patch("app.rag.client.OpenAI", return_value=mock_client):
        yield mock_client


# ── _textualize_product ─────────────────────────────────────────────────


class TestTextualizeProduct:
    def test_minimal_product(self):
        result = rag.products._textualize_product({"name": "Widget"})
        assert "Product: Widget" in result
        assert "SKU/ID:" not in result
        assert "Category:" not in result
        assert "Price:" not in result

    def test_full_product(self):
        p = {
            "name": "Pro Widget",
            "product_id": "PW-001",
            "category": "Widgets",
            "price": 2999,
            "currency": "USD",
            "description": "A professional widget",
            "attributes": {"color": "red", "size": "M"},
            "stock_status": "in_stock",
            "image_url": "https://example.com/img.png",
            "product_url": "https://example.com/pw-001",
        }
        result = rag.products._textualize_product(p)
        assert "Product: Pro Widget" in result
        assert "SKU/ID: PW-001" in result
        assert "Category: Widgets" in result
        assert "29.99 USD" in result
        assert "Description: A professional widget" in result
        assert "stock" in result.lower()
        assert "Image:" in result or "image:" in result
        assert "URL:" in result or "url:" in result

    def test_price_in_cents_converts_to_dollars(self):
        p = {"name": "X", "price": 1000}
        result = rag.products._textualize_product(p)
        assert "10.00" in result

    def test_int_price_none(self):
        p = {"name": "X", "price": None}
        result = rag.products._textualize_product(p)
        assert "Price:" not in result

    def test_float_price(self):
        p = {"name": "X", "price": 19.99}
        result = rag.products._textualize_product(p)
        # Float 19.99 has a decimal point → treated as dollars (not cents)
        assert "19.99" in result

    def test_attributes_as_dict(self):
        p = {"name": "X", "attributes": {"color": "blue", "size": "L"}}
        result = rag.products._textualize_product(p)
        assert "color=blue" in result
        assert "size=L" in result

    def test_attributes_empty(self):
        p = {"name": "X", "attributes": {}}
        result = rag.products._textualize_product(p)
        assert "Attributes:" not in result

    def test_empty_name(self):
        p = {"name": ""}
        result = rag.products._textualize_product(p)
        assert "Product: " in result

    def test_missing_keys(self):
        p = {"name": "X"}
        result = rag.products._textualize_product(p)
        assert "Product: X" in result
        assert "Category:" not in result  # key not present → .get returns None


# ── index_products ────────────────────────────────────────────────────


class TestIndexProducts:
    def test_empty_list(self, tenant_id, mock_chroma, mock_openai):
        col, _ = mock_chroma
        result = rag.index_products(tenant_id, [], import_batch="test")
        assert result == 0
        col.add.assert_not_called()

    def test_index_single_product(self, tenant_id, mock_chroma, mock_openai):
        col, _ = mock_chroma
        products = [{"name": "Widget", "product_id": "W001", "price": 2999}]
        result = rag.index_products(tenant_id, products, import_batch="b1")
        assert result == 1
        col.add.assert_called_once()
        call_args = col.add.call_args[1]
        assert len(call_args["ids"]) == 1
        assert "product-b1-W001" in call_args["ids"][0]
        assert call_args["metadatas"][0]["type"] == "product"
        assert call_args["metadatas"][0]["import_batch"] == "b1"
        assert call_args["metadatas"][0]["product_id"] == "W001"
        assert "Product: Widget" in call_args["documents"][0]

    def test_index_multiple_products(self, tenant_id, mock_chroma, mock_openai):
        col, _ = mock_chroma
        products = [
            {"name": "A", "product_id": "A1"},
            {"name": "B", "product_id": "B2"},
        ]
        result = rag.index_products(tenant_id, products, import_batch="b2")
        assert result == 2
        assert col.add.call_args[1]["ids"] == [
            "product-b2-A1",
            "product-b2-B2",
        ]

    def test_index_clears_prior_batch(self, tenant_id, mock_chroma, mock_openai):
        col, _ = mock_chroma
        products = [{"name": "X", "product_id": "X1"}]
        rag.index_products(tenant_id, products, import_batch="b1")
        col.delete.assert_any_call(where={"$and": [{"type": "product"}, {"import_batch": "b1"}]})

    def test_index_handles_delete_failure(self, tenant_id, mock_chroma, mock_openai):
        col, _ = mock_chroma
        col.delete.side_effect = Exception("Chroma error")
        products = [{"name": "Y", "product_id": "Y1"}]
        result = rag.index_products(tenant_id, products, import_batch="b1")
        assert result == 1  # still indexes despite delete error
        col.add.assert_called_once()

    def test_index_product_without_id(self, tenant_id, mock_chroma, mock_openai):
        col, _ = mock_chroma
        products = [{"name": "NoID"}]
        result = rag.index_products(tenant_id, products, import_batch="b1")
        assert result == 1
        ids = col.add.call_args[1]["ids"]
        assert "unknown" in ids[0] or "product-b1-unknown" in ids[0]

    def test_index_no_batch_string(self, tenant_id, mock_chroma, mock_openai):
        col, _ = mock_chroma
        products = [{"name": "X", "product_id": "X1"}]
        rag.index_products(tenant_id, products, import_batch="")
        call_args = col.add.call_args[1]
        assert call_args["metadatas"][0]["import_batch"] == ""
        assert "product--X1" not in call_args["ids"][0]
        assert "product-X1" in call_args["ids"][0]


# ── delete_products_by_batch ───────────────────────────────────────────


class TestDeleteProductsByBatch:
    def test_delete_existing_batch(self, tenant_id, mock_chroma):
        col, _ = mock_chroma
        col.count.side_effect = [10, 0]
        result = rag.delete_products_by_batch(tenant_id, "b1")
        assert result == 10
        col.delete.assert_called_once_with(
            where={"$and": [{"type": "product"}, {"import_batch": "b1"}]}
        )

    def test_delete_nonexistent_batch(self, tenant_id, mock_chroma):
        col, _ = mock_chroma
        col.count.side_effect = [0, 0]
        result = rag.delete_products_by_batch(tenant_id, "nonexistent")
        assert result == 0
        col.delete.assert_called_once()

    def test_delete_exception_returns_zero(self, tenant_id, mock_chroma):
        col, _ = mock_chroma
        col.delete.side_effect = Exception("Chroma error")
        result = rag.delete_products_by_batch(tenant_id, "b1")
        assert result == 0

    def test_delete_count_mismatch_still_returns_diff(self, tenant_id, mock_chroma):
        col, _ = mock_chroma
        col.count.side_effect = [5, 2]
        result = rag.delete_products_by_batch(tenant_id, "b1")
        assert result == 3


# ── search with where filter ──────────────────────────────────────────


class TestSearchWithWhere:
    def test_where_passed_to_query(self, tenant_id, mock_chroma, mock_openai):
        col, _ = mock_chroma
        col.count.return_value = 5
        col.query.return_value = {
            "ids": [["id1"]],
            "documents": [["doc"]],
            "metadatas": [[{"type": "product", "filename": "cat.csv"}]],
            "distances": [[0.3]],
        }
        rag.search(tenant_id, "test", where={"type": "product"}, threshold=0.99)
        call_kwargs = col.query.call_args[1]
        assert call_kwargs["where"] == {"type": "product"}

    def test_where_not_passed_when_none(self, tenant_id, mock_chroma, mock_openai):
        col, _ = mock_chroma
        col.count.return_value = 5
        col.query.return_value = {
            "ids": [["id1"]],
            "documents": [["doc"]],
            "metadatas": [[{"filename": "doc.txt"}]],
            "distances": [[0.3]],
        }
        rag.search(tenant_id, "test", threshold=0.99)
        call_kwargs = col.query.call_args[1]
        assert "where" not in call_kwargs

    def test_where_with_custom_top_k(self, tenant_id, mock_chroma, mock_openai):
        col, _ = mock_chroma
        col.count.return_value = 50
        col.query.return_value = {
            "ids": [["id1"]],
            "documents": [["doc"]],
            "metadatas": [[{"type": "product", "filename": "cat.csv"}]],
            "distances": [[0.3]],
        }
        rag.search(tenant_id, "test", top_k=3, where={"type": "product"}, threshold=0.99)
        call_kwargs = col.query.call_args[1]
        assert call_kwargs["where"] == {"type": "product"}
        assert call_kwargs["n_results"] == 3

    def test_where_filters_properly(self, tenant_id, mock_chroma, mock_openai):
        """Verify that different where filters produce different query kwargs."""
        col, _ = mock_chroma
        col.count.return_value = 5
        col.query.return_value = {
            "ids": [["id1"]],
            "documents": [["doc"]],
            "metadatas": [[{"type": "product", "category": "Electronics"}]],
            "distances": [[0.3]],
        }

        rag.search(tenant_id, "test", where={"type": "product", "category": "Electronics"}, threshold=0.99)
        call_kwargs = col.query.call_args[1]
        assert call_kwargs["where"]["type"] == "product"
        assert call_kwargs["where"]["category"] == "Electronics"


# ── Edge cases ──────────────────────────────────────────────────────────


class TestTextualizeProductEdgeCases:
    def test_very_long_name(self):
        name = "X" * 1000
        result = rag.products._textualize_product({"name": name})
        assert len(result) > 100
        assert name in result

    def test_float_price_with_cents_zero(self):
        p = {"name": "X", "price": 19.00}
        result = rag.products._textualize_product(p)
        assert "19.00" in result

    def test_unicode_in_fields(self):
        p = {"name": "Café", "description": "Crème brûlée €5"}
        result = rag.products._textualize_product(p)
        assert "Café" in result
        assert "Crème brûlée" in result

    def test_int_product_id(self):
        p = {"name": "X", "product_id": 12345}
        result = rag.products._textualize_product(p)
        assert "12345" in result

    def test_none_attributes(self):
        p = {"name": "X", "attributes": None}
        result = rag.products._textualize_product(p)
        assert "Attributes:" not in result

    def test_non_numeric_price_returns_none_in_text(self):
        p = {"name": "X", "price": None}
        result = rag.products._textualize_product(p)
        assert "Price:" not in result

    def test_zero_price(self):
        p = {"name": "X", "price": 0}
        result = rag.products._textualize_product(p)
        assert "0.00" in result

    def test_none_description(self):
        p = {"name": "X", "description": None}
        result = rag.products._textualize_product(p)
        assert "Description:" not in result

    def test_empty_stock_status_excluded(self):
        p = {"name": "X", "stock_status": ""}
        result = rag.products._textualize_product(p)
        assert "Stock:" not in result  # empty string is falsy, excluded

    def test_none_image_url(self):
        p = {"name": "X", "image_url": None}
        result = rag.products._textualize_product(p)
        assert "Image:" not in result

    def test_none_product_url(self):
        p = {"name": "X", "product_url": None}
        result = rag.products._textualize_product(p)
        assert "URL:" not in result


class TestIndexProductsEdgeCases:
    def test_duplicate_product_ids_in_same_batch(self, tenant_id, mock_chroma, mock_openai):
        col, _ = mock_chroma
        products = [
            {"name": "A", "product_id": "ID1"},
            {"name": "B", "product_id": "ID1"},
        ]
        result = rag.index_products(tenant_id, products, import_batch="b1")
        assert result == 2
        ids = col.add.call_args[1]["ids"]
        assert ids == ["product-b1-ID1", "product-b1-ID1"]

    def test_empty_product_id_string(self, tenant_id, mock_chroma, mock_openai):
        col, _ = mock_chroma
        products = [{"name": "X", "product_id": ""}]
        result = rag.index_products(tenant_id, products, import_batch="b1")
        assert result == 1
        id_ = col.add.call_args[1]["ids"][0]
        assert "unknown" in id_

    def test_empty_product_id_no_batch(self, tenant_id, mock_chroma, mock_openai):
        col, _ = mock_chroma
        products = [{"name": "X", "product_id": ""}]
        result = rag.index_products(tenant_id, products, import_batch="")
        assert result == 1
        id_ = col.add.call_args[1]["ids"][0]
        assert "unknown" in id_

    def test_many_products(self, tenant_id, mock_chroma, mock_openai):
        col, _ = mock_chroma
        products = [{"name": f"P{i}", "product_id": f"ID{i}"} for i in range(50)]
        result = rag.index_products(tenant_id, products, import_batch="big")
        assert result == 50
        assert len(col.add.call_args[1]["ids"]) == 50


class TestDeleteProductsByBatchEdgeCases:
    def test_delete_special_chars_in_batch(self, tenant_id, mock_chroma):
        col, _ = mock_chroma
        col.count.side_effect = [3, 0]
        result = rag.delete_products_by_batch(tenant_id, "batch/with/slashes")
        assert result == 3
        col.delete.assert_called_once_with(
            where={"$and": [{"type": "product"}, {"import_batch": "batch/with/slashes"}]}
        )

    def test_delete_empty_batch_string(self, tenant_id, mock_chroma):
        col, _ = mock_chroma
        col.count.side_effect = [0, 0]
        result = rag.delete_products_by_batch(tenant_id, "")
        assert result == 0


class TestSearchWithWhereEdgeCases:
    def test_where_no_results(self, tenant_id, mock_chroma, mock_openai):
        col, _ = mock_chroma
        col.count.return_value = 5
        col.query.return_value = {
            "ids": [[]],
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }
        results = rag.search(tenant_id, "test", where={"type": "nonexistent"}, threshold=0.99)
        assert results == []

    def test_where_with_empty_dict_is_skipped(self, tenant_id, mock_chroma, mock_openai):
        col, _ = mock_chroma
        col.count.return_value = 5
        col.query.return_value = {
            "ids": [["id1"]],
            "documents": [["doc"]],
            "metadatas": [[{"type": "product"}]],
            "distances": [[0.3]],
        }
        rag.search(tenant_id, "test", where={}, threshold=0.99)
        call_kwargs = col.query.call_args[1]
        assert "where" not in call_kwargs  # empty dict is falsy, not passed
