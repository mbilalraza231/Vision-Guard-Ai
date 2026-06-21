-- ==========================================
-- VISION GUARD AI - SUPABASE SCHEMA SETUP
-- ==========================================
-- This script sets up the 'profiles' table and automatic 
-- synchronization from auth.users.
-- Run this in your Supabase SQL Editor.

-- 1. Create the profiles table in the public schema
CREATE TABLE IF NOT EXISTS public.profiles (
  id UUID REFERENCES auth.users ON DELETE CASCADE NOT NULL PRIMARY KEY,
  email TEXT NOT NULL,
  name TEXT,
  role TEXT DEFAULT 'viewer' CHECK (role IN ('admin', 'manager', 'officer', 'viewer')),
  status TEXT DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
  avatar TEXT,
  "createdAt" TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 2. Enable Row Level Security (RLS)
-- This ensures data can only be accessed according to the policies below.
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

-- 3. Create RLS Policies
-- Policy: Allow authenticated users to view all profiles (needed for the dashboard list)
CREATE POLICY "Profiles are viewable by authenticated users" 
ON public.profiles FOR SELECT 
TO authenticated 
USING (true);

-- Policy: Allow users to update their own profile data
CREATE POLICY "Users can update own profile" 
ON public.profiles FOR UPDATE 
TO authenticated 
USING (auth.uid() = id);

-- 4. Create a Database Function to handle new user signups
-- This function extracts metadata (like name/role) and creates a public profile row.
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger AS $$
BEGIN
  INSERT INTO public.profiles (id, email, name, role, status)
  VALUES (
    new.id, 
    new.email, 
    COALESCE(new.raw_user_meta_data->>'name', split_part(new.email, '@', 1)),
    COALESCE(new.raw_user_meta_data->>'role', 'viewer'),
    'inactive'
  );
  RETURN new;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 5. Create a Trigger to call the function automatically
-- This fires every time a new row is inserted into auth.users (on signup).
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- ==========================================
-- INITIAL DATA (Optional)
-- ==========================================
-- If you already have users in auth.users, run this once to backfill profiles:
-- INSERT INTO public.profiles (id, email, name, role, status)
-- SELECT id, email, email, 'admin', 'active' FROM auth.users
-- ON CONFLICT (id) DO NOTHING;
