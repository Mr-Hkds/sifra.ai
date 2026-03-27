-- Run this entire script in your Supabase SQL Editor

-- 1. Enable the pgvector extension
create extension if not exists vector;

-- 2. Add the mathematical vector column to your memories table (768 for Gemini)
alter table memories add column if not exists embedding vector(768);

-- 3. Create the 'match_memories' function for Cosine Similarity search
create or replace function match_memories (
  query_embedding vector(768),
  match_threshold float,
  match_count int
)
returns table (
  id uuid,
  content text,
  category text,
  importance int,
  decay_score float,
  times_referenced int,
  last_referenced timestamp with time zone,
  similarity float
)
language sql stable
as $$
  select
    memories.id,
    memories.content,
    memories.category,
    memories.importance,
    memories.decay_score,
    memories.times_referenced,
    memories.last_referenced,
    1 - (memories.embedding <=> query_embedding) as similarity
  from memories
  where memories.embedding is not null
    and 1 - (memories.embedding <=> query_embedding) > match_threshold
    and memories.category != 'forget'
  order by memories.embedding <=> query_embedding
  limit match_count;
$$;
