"""Preload the ONNX embedding model during Docker build."""
from chromadb.utils import embedding_functions

ef = embedding_functions.DefaultEmbeddingFunction()
# Trigger actual download by embedding sample text
ef(["hello world"])
print("ONNX model cached successfully")
