from student_api import rag_embedding_shift, rag_length_shift


def test_rag_length_collapse_is_detected():
    baseline_batch_means = [40, 42, 39, 41, 43, 40, 42]
    current_texts = ["x y", "a b c", "one two"]
    assert rag_length_shift(current_texts, baseline_batch_means)["is_anomaly"] is True


def test_rag_embedding_shift_is_detected():
    baseline_norms = [1.00, 1.02, 0.99, 1.01, 0.98, 1.00, 1.01]
    current_norms = [2.50, 2.60, 2.45, 2.55]
    res = rag_embedding_shift(current_norms, baseline_norms)
    assert res["is_anomaly"] is True

