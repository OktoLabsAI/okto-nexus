// Display metadata never becomes a different canonical agent identity.
export function displayName(metadata: Record<string, unknown> | null | undefined): string {
  return typeof metadata?.display_name === 'string' ? metadata.display_name : '';
}

export function otherMetadata(metadata: Record<string, unknown> | null | undefined): Record<string, unknown> {
  const result = {...metadata};
  if (typeof result.display_name === 'string') delete result.display_name;
  return result;
}

export function identityMetadata(metadata: Record<string, unknown>, name: string): Record<string, unknown> {
  return name.trim() ? {...metadata, display_name: name.trim()} : {...metadata};
}
