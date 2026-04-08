import json
import pickle
from functools import wraps
from typing import Any, Optional, Callable
from datetime import datetime, timedelta

import redis
from app.core.config import get_settings

settings = get_settings()

# Redis client singleton
redis_client = None

def get_redis_client():
    """Get or create Redis client"""
    global redis_client
    if redis_client is None:
        try:
            redis_url = getattr(settings, 'REDIS_URL', 'redis://localhost:6379/0')
            redis_client = redis.from_url(redis_url, decode_responses=False)
        except Exception as e:
            print(f"Redis connection failed: {e}")
            return None
    return redis_client

class CacheManager:
    """Production-ready caching layer with Redis fallback to memory"""
    
    # In-memory cache fallback
    _memory_cache: dict = {}
    _memory_ttl: dict = {}
    
    DEFAULT_TTL = 300  # 5 minutes default
    
    @classmethod
    def get(cls, key: str) -> Optional[Any]:
        """Get value from cache"""
        # Try Redis first
        redis = get_redis_client()
        if redis:
            try:
                value = redis.get(key)
                if value:
                    return pickle.loads(value)
            except Exception as e:
                print(f"Redis get error: {e}")
        
        # Fallback to memory cache
        if key in cls._memory_cache:
            if datetime.utcnow() < cls._memory_ttl.get(key, datetime.utcnow()):
                return cls._memory_cache[key]
            else:
                # Expired
                cls.delete(key)
        
        return None
    
    @classmethod
    def set(cls, key: str, value: Any, ttl: int = DEFAULT_TTL) -> bool:
        """Set value in cache"""
        try:
            # Try Redis first
            redis = get_redis_client()
            if redis:
                serialized = pickle.dumps(value)
                redis.setex(key, ttl, serialized)
                return True
        except Exception as e:
            print(f"Redis set error: {e}")
        
        # Fallback to memory cache
        cls._memory_cache[key] = value
        cls._memory_ttl[key] = datetime.utcnow() + timedelta(seconds=ttl)
        return True
    
    @classmethod
    def delete(cls, key: str) -> bool:
        """Delete value from cache"""
        # Try Redis
        redis = get_redis_client()
        if redis:
            try:
                redis.delete(key)
            except Exception as e:
                print(f"Redis delete error: {e}")
        
        # Memory cache
        cls._memory_cache.pop(key, None)
        cls._memory_ttl.pop(key, None)
        return True
    
    @classmethod
    def clear_pattern(cls, pattern: str) -> bool:
        """Clear all keys matching pattern"""
        redis = get_redis_client()
        if redis:
            try:
                for key in redis.scan_iter(match=pattern):
                    redis.delete(key)
            except Exception as e:
                print(f"Redis clear pattern error: {e}")
        
        # Clear memory cache keys matching pattern
        keys_to_remove = [k for k in cls._memory_cache.keys() if pattern.replace('*', '') in k]
        for key in keys_to_remove:
            cls._memory_cache.pop(key, None)
            cls._memory_ttl.pop(key, None)
        
        return True

def cached(ttl: int = 300, key_prefix: str = "cache"):
    """Decorator for caching function results"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key
            key_parts = [key_prefix, func.__name__]
            
            # Hash args
            for arg in args:
                if isinstance(arg, (str, int, float, bool)):
                    key_parts.append(str(arg))
                elif hasattr(arg, 'id'):
                    key_parts.append(str(arg.id))
            
            # Hash kwargs
            for k, v in sorted(kwargs.items()):
                if isinstance(v, (str, int, float, bool)):
                    key_parts.append(f"{k}:{v}")
            
            cache_key = ":".join(key_parts)
            
            # Try cache
            cached_value = CacheManager.get(cache_key)
            if cached_value is not None:
                return cached_value
            
            # Execute function
            result = func(*args, **kwargs)
            
            # Cache result
            CacheManager.set(cache_key, result, ttl)
            
            return result
        
        return wrapper
    return decorator

def invalidate_cache(pattern: str):
    """Invalidate cache entries matching pattern"""
    return CacheManager.clear_pattern(pattern)

# API Rate Limiting Helpers
class RateLimiter:
    """Simple rate limiting using Redis/counter"""
    
    @classmethod
    def is_allowed(cls, key: str, max_requests: int, window_seconds: int) -> bool:
        """Check if request is allowed under rate limit"""
        redis = get_redis_client()
        if not redis:
            # Allow if no Redis
            return True
        
        try:
            pipe = redis.pipeline()
            now = int(datetime.utcnow().timestamp())
            window_start = now - window_seconds
            
            # Remove old entries
            pipe.zremrangebyscore(key, 0, window_start)
            
            # Count current
            pipe.zcard(key)
            
            # Add current request
            pipe.zadd(key, {str(now): now})
            
            # Set expiry
            pipe.expire(key, window_seconds)
            
            results = pipe.execute()
            current_count = results[1]
            
            return current_count < max_requests
            
        except Exception as e:
            print(f"Rate limiting error: {e}")
            return True  # Allow on error
