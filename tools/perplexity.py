"""
Perplexity AI integration for real-time web search with citations
"""
import aiohttp
import asyncio
from typing import List, Dict, Optional
from core.config import settings
from core.logger import setup_logger

logger = setup_logger(__name__)

class PerplexitySearch:
    """Perplexity AI search integration"""
    
    def __init__(self):
        self.api_key = settings.PERPLEXITY_API_KEY
        self.base_url = "https://api.perplexity.ai/chat/completions"
        self.model = settings.PERPLEXITY_MODEL
        logger.info(f"Perplexity initialized (model: {self.model})")
    
    async def search(
        self, 
        query: str, 
        max_tokens: int = 1000,
        return_citations: bool = True
    ) -> Dict[str, any]:
        """
        Perform web search using Perplexity AI
        
        Args:
            query: Search query
            max_tokens: Max response tokens
            return_citations: Include source citations
            
        Returns:
            Dict with 'answer' and optionally 'citations'
        """
        logger.info(f"Perplexity search: {query[:100]}")
        
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                
                payload = {
                    "model": self.model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a helpful search assistant. Provide accurate, well-cited answers based on current information."
                        },
                        {
                            "role": "user",
                            "content": query
                        }
                    ],
                    "max_tokens": max_tokens,
                    "temperature": 0.2,
                    "return_citations": return_citations,
                    "search_recency_filter": "month"  # Focus on recent results
                }
                
                async with session.post(
                    self.base_url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Perplexity API error {response.status}: {error_text}")
                        return {
                            "answer": f"Search error: {response.status}",
                            "citations": []
                        }
                    
                    data = await response.json()
                    answer = data['choices'][0]['message']['content']
                    citations = data.get('citations', [])
                    
                    logger.info(f"Perplexity result: {len(answer)} chars, {len(citations)} citations")
                    
                    return {
                        "answer": answer,
                        "citations": citations,
                        "model": data.get('model'),
                        "usage": data.get('usage')
                    }
                    
        except asyncio.TimeoutError:
            logger.error("Perplexity search timeout")
            return {
                "answer": "Search timed out. Please try again.",
                "citations": []
            }
        except Exception as e:
            logger.error(f"Perplexity search error: {e}")
            return {
                "answer": f"Search error: {str(e)}",
                "citations": []
            }
    
    async def quick_search(self, query: str) -> str:
        """Quick search returning just the answer text"""
        result = await self.search(query, max_tokens=500)
        return result['answer']

# Global perplexity instance
perplexity = PerplexitySearch()
