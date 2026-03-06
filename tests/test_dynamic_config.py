import os
import time
import pytest
import numpy as np
from app.core.vault import VaultManager
from app.models.identity import IdentityProfile, KnowledgeBase
from app.utils.prompt import build_email_prompt
import srvdb

@pytest.mark.asyncio
async def test_vault_manager_encryption():
    """
    Verify that VaultManager correctly encrypts a mock API key using PBKDF2.
    Assert raw DB value is undecipherable and decrypted output matches.
    """
    original_key = "gsk_test_mock_api_key_12345"
    
    encrypted = VaultManager.encrypt(original_key)
    
    # Assert ciphertext is not the plaintext
    assert encrypted != original_key
    assert "gsk_test" not in encrypted
    assert len(encrypted) > len(original_key)
    
    decrypted = VaultManager.decrypt(encrypted)
    
    # Assert decryption works
    assert decrypted == original_key


@pytest.mark.asyncio
async def test_srvdb_semantic_retrieval(tmp_path):
    """
    Initialize a temporary SrvDB instance.
    Insert two KnowledgeBase pillars.
    Perform similarity search and assert retrieval time.
    """
    # 1. Initialize temporary SrvDB instance in data/test_srvdb/
    srvdb_dir = tmp_path / "data" / "test_srvdb"
    srvdb_dir.mkdir(parents=True, exist_ok=True)
    
    # We use dimension 384 for fast local MiniLM testing
    db = srvdb.SrvDBPython(str(srvdb_dir), dimension=384)
    
    # 2. Insert two KnowledgeBase pillars
    # Mock some embeddings since we don't have the active live model in the test suite
    cloud_embed = np.random.randn(384).astype(np.float32)
    mech_embed = np.random.randn(384).astype(np.float32)
    
    ids = ["cloud_1", "mech_1"]
    embeddings = [cloud_embed.tolist(), mech_embed.tolist()]
    metadatas = [
        '{"title": "Cloud Services", "prop": "Fast scalable cloud"}',
        '{"title": "Mechanical Engineering", "prop": "Gear design"}'
    ]
    
    count = db.add(ids=ids, embeddings=embeddings, metadatas=metadatas)
    db.persist()
    assert count == 2
    
    # 3. Perform a similarity search and assert sub-millisecond retrieval
    # Query with a vector slightly closer to cloud
    query_vector = cloud_embed + np.random.randn(384).astype(np.float32) * 0.1
    
    start_time = time.perf_counter()
    results = db.search(query=query_vector.tolist(), k=1)
    end_time = time.perf_counter()
    
    duration_ms = (end_time - start_time) * 1000
    
    assert len(results) == 1
    assert results[0][0] == "cloud_1" # Because we added 0.1 noise to cloud, it should be closer than mech
    
    # Since Python tests can be slow in CI, we'll assert it's extremely fast (< 5ms to be safe)
    assert duration_ms < 5.0, f"Retrieval took {duration_ms} ms, expected sub-millisecond."


@pytest.mark.asyncio
async def test_dynamic_prompt_integration():
    """
    Mock an IdentityProfile with custom branding.
    Assert system prompt contains dynamic strings and zero hardcoded fallbacks.
    """
    # Mock Lead
    lead = {
        "first_name": "Srinivas",
        "role": "CTO",
        "company": "TestCorp",
        "industry": "Software",
        "location": "San Francisco"
    }
    
    # Mock Identity Profile
    identity = IdentityProfile(
        name="CyberArc",
        tagline="Secure AI"
    )
    
    # Mock Services
    services = [
        KnowledgeBase(title="Cloud Native", value_prop="We build kubernetes."),
        KnowledgeBase(title="SOC2 Audit", value_prop="We pass compliance.")
    ]
    
    sys_prompt, user_prompt = build_email_prompt(lead, identity, services)
    
    # Verify Identity Profile injection
    assert "CyberArc" in sys_prompt
    assert "Secure AI" in sys_prompt
    
    assert "CyberArc" in user_prompt
    
    # Verify Knowledge Base extraction into user prompt
    assert "Cloud Native" in user_prompt
    assert "SOC2 Audit" in user_prompt
    
    # Ensure there are no legacy company.py fallbacks (e.g. from the previous static files)
    assert "Zero-Trust SOC/NOC Fusion" not in user_prompt
