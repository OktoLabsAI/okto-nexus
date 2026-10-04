import type { HarnessConfiguration } from './runtimeApi';

export function harnessFieldValues(schema: HarnessConfiguration, name: string, settings: Record<string, string>): string[] {
  const field = schema.parameters.find(p => p.name === name);
  if (name === 'model' && schema.adapter_id === 'pi_rpc' && settings.provider && schema.models.length) {
    return schema.models.filter(m => m.provider === settings.provider).map(m => m.id);
  }
  if (name === 'effort' && schema.adapter_id === 'codex_app_server' && settings.model && schema.models.length) {
    return schema.models.find(m => m.id === settings.model)?.efforts ?? [];
  }
  return field?.values ?? [];
}

export function harnessSelectionError(schema: HarnessConfiguration, settings: Record<string, string>): string | null {
  for (const [name, value] of Object.entries(settings)) {
    if (!schema.parameters.some(field => field.name === name && field.core_applies) ||
        typeof value !== 'string' || value.length > 200 || /[\x00-\x1f]/.test(value)) {
      return 'Parâmetro desconhecido ou valor inválido para este harness.';
    }
  }
  for (const field of schema.parameters) {
    const value = settings[field.name];
    const choices = harnessFieldValues(schema, field.name, settings);
    const modelEffort = field.name === 'effort' && schema.adapter_id === 'codex_app_server' && !!settings.model && !!schema.models.length;
    if (value && (field.type === 'enum' || modelEffort) && !choices.includes(value)) {
      return `${field.label}: escolha um valor compatível com o harness e o modelo selecionados.`;
    }
    if (!value && schema.constraints?.[field.name] && field.default_source === 'core_adapter' && !choices.includes(String(field.default))) {
      return `${field.label}: a política do harness exige uma escolha explícita.`;
    }
  }
  if (schema.adapter_id === 'pi_rpc' && settings.model && schema.models.length) {
    const matches = schema.models.filter(m => m.id === settings.model && (!settings.provider || m.provider === settings.provider));
    if (matches.length !== 1) return 'Selecione o provedor deste modelo.';
  }
  return null;
}

export function parseHarnessConfigurationFile(text: string, schema: HarnessConfiguration): Record<string, string> {
  if (new TextEncoder().encode(text).length > 65536) throw new Error('O arquivo deve ter no máximo 64 KiB.');
  const document = JSON.parse(text.replace(/^\uFEFF/, ''));
  if (!document || Array.isArray(document) || typeof document !== 'object' ||
      Object.keys(document).sort().join(',') !== 'adapter_id,format,settings,version' ||
      document.format !== 'nexus-harness-config' || document.version !== 1 || document.adapter_id !== schema.adapter_id ||
      !document.settings || Array.isArray(document.settings) || typeof document.settings !== 'object') {
    throw new Error('Selecione um arquivo nexus-harness-config versão 1 para este harness.');
  }
  const error = harnessSelectionError(schema, document.settings);
  if (error) throw new Error(error);
  if (Object.values(document.settings).some(value => value === '')) throw new Error('Omita parâmetros vazios para usar o padrão.');
  return {...document.settings};
}

export function harnessConfigurationFile(adapterId: string, settings: Record<string, string>): string {
  return JSON.stringify({format: 'nexus-harness-config', version: 1, adapter_id: adapterId,
    settings: Object.fromEntries(Object.entries(settings).filter(([, value]) => value !== ''))}, null, 2) + '\n';
}
