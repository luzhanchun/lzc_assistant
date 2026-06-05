/**
 * Agent-aware tool selector.
 *
 * Loads the backend tool manifest and shows the tools available to the active
 * agent, grouped as local tools, MCP tools, and subagent tools.
 */

import { memo, useCallback, useEffect, useMemo, useState } from 'react';
import {
  Bot,
  Check,
  ChevronDown,
  ChevronUp,
  Globe,
  Info,
  Loader2,
  Wrench,
} from 'lucide-react';
import type { AgentToolManifestItem, ServerInfo, ToolSchema } from '../../types';
import { getAgentToolManifest } from '../../services/api/agent';
import { DEFAULT_AGENT_NAME } from '../../constants';

export interface ToolSelectorProps {
  token?: string;
  agentName: string;
  selectedToolsByAgent: Record<string, string[]>;
  onAgentChange: (agentName: string) => void;
  onSelectionChange: (agentName: string, tools: string[]) => void;
  disabled?: boolean;
  onExpandChange?: (isExpanded: boolean) => void;
}

const CATEGORY_CONFIG = {
  tool: {
    label: 'Tools',
    icon: Wrench,
    activeClass: 'bg-orange-100 dark:bg-orange-900/30 text-orange-800 dark:text-orange-200',
    hoverClass: 'hover:bg-orange-50 dark:hover:bg-orange-900/20',
    iconClass: 'text-orange-500',
  },
  mcp: {
    label: 'MCP',
    icon: Globe,
    activeClass: 'bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-200',
    hoverClass: 'hover:bg-blue-50 dark:hover:bg-blue-900/20',
    iconClass: 'text-blue-500',
  },
  subagent: {
    label: 'Subagent',
    icon: Bot,
    activeClass: 'bg-purple-100 dark:bg-purple-900/30 text-purple-800 dark:text-purple-200',
    hoverClass: 'hover:bg-purple-50 dark:hover:bg-purple-900/20',
    iconClass: 'text-purple-500',
  },
} as const;

type Category = keyof typeof CATEGORY_CONFIG;

const ToolChip = memo(function ToolChip({
  tool,
  serverType,
  isSelected,
  isShowingInfo,
  onToggle,
  onShowInfo,
  disabled,
}: {
  tool: ToolSchema;
  serverType: ServerInfo['type'];
  isSelected: boolean;
  isShowingInfo: boolean;
  onToggle: () => void;
  onShowInfo: () => void;
  disabled?: boolean;
}) {
  const displayName = serverType === 'mcp'
    ? tool.name.replace(/^mcp_\w+_/, '')
    : tool.name.replace(/^subagent_/, '');
  const selectedClass = serverType === 'local'
    ? 'bg-orange-500'
    : serverType === 'mcp'
      ? 'bg-blue-500'
      : 'bg-purple-500';

  return (
    <div
      className={`
        inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs
        transition-colors duration-150
        ${disabled ? 'opacity-50' : ''}
        ${isSelected
          ? `${selectedClass} text-white`
          : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300'
        }
      `}
    >
      <button
        type="button"
        onClick={() => !disabled && onToggle()}
        className="flex items-center gap-1 cursor-pointer"
        disabled={disabled}
      >
        {isSelected && <Check className="w-3 h-3" />}
        <span>{displayName}</span>
      </button>

      {tool.description && (
        <Info
          onClick={(event) => {
            event.stopPropagation();
            onShowInfo();
          }}
          className={`
            w-3 h-3 cursor-pointer flex-shrink-0
            ${isShowingInfo ? 'text-yellow-300' : 'text-gray-400 hover:text-gray-500'}
          `}
        />
      )}
    </div>
  );
});

const ServerCard = memo(function ServerCard({
  server,
  selectedTools,
  onToggleTool,
  onToggleAll,
  isExpanded,
  onToggleExpand,
  disabled,
}: {
  server: ServerInfo;
  selectedTools: string[];
  onToggleTool: (toolName: string) => void;
  onToggleAll: (server: ServerInfo, select: boolean) => void;
  isExpanded: boolean;
  onToggleExpand: () => void;
  disabled?: boolean;
}) {
  const [showingInfoTool, setShowingInfoTool] = useState<string | null>(null);
  const selectedCount = server.tools.filter(tool => selectedTools.includes(tool.name)).length;
  const allSelected = server.tools.length > 0 && selectedCount === server.tools.length;
  const infoTool = showingInfoTool
    ? server.tools.find(tool => tool.name === showingInfoTool)
    : null;
  const ServerIcon = server.type === 'local' ? Wrench : server.type === 'mcp' ? Globe : Bot;

  return (
    <div className="border border-gray-200 dark:border-gray-600 rounded-lg overflow-hidden">
      <div
        className="flex items-center gap-2 px-3 py-2 bg-gray-50 dark:bg-gray-700/50 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700"
        onClick={onToggleExpand}
      >
        <ServerIcon className="w-3.5 h-3.5 text-gray-500" />
        <span className="text-xs font-medium text-gray-700 dark:text-gray-300 flex-1">
          {server.name}
        </span>
        <span className="text-xs text-gray-500 dark:text-gray-400">
          {selectedCount}/{server.tools.length}
        </span>
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            onToggleAll(server, !allSelected);
          }}
          disabled={disabled}
          className="px-2 py-0.5 text-xs rounded bg-gray-100 dark:bg-gray-600 text-gray-600 dark:text-gray-300 hover:opacity-80"
        >
          {allSelected ? 'Deselect All' : 'Select All'}
        </button>
        {isExpanded ? (
          <ChevronUp className="w-4 h-4 text-gray-400" />
        ) : (
          <ChevronDown className="w-4 h-4 text-gray-400" />
        )}
      </div>

      {isExpanded && (
        <div className="p-2 bg-gray-50 dark:bg-gray-800">
          <div className="flex flex-wrap gap-1.5">
            {server.tools.map(tool => (
              <ToolChip
                key={tool.name}
                tool={tool}
                serverType={server.type}
                isSelected={selectedTools.includes(tool.name)}
                onToggle={() => onToggleTool(tool.name)}
                onShowInfo={() => {
                  setShowingInfoTool(prev => prev === tool.name ? null : tool.name);
                }}
                isShowingInfo={showingInfoTool === tool.name}
                disabled={disabled}
              />
            ))}
          </div>

          {infoTool && (
            <div className="mt-2 p-2 bg-gray-100 dark:bg-gray-700 rounded-lg">
              <div className="text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                {infoTool.name}
              </div>
              <div className="text-xs text-gray-600 dark:text-gray-400">
                {infoTool.description}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
});

export function ToolSelector({
  token,
  agentName,
  selectedToolsByAgent,
  onAgentChange,
  onSelectionChange,
  disabled = false,
  onExpandChange,
}: ToolSelectorProps) {
  const [manifest, setManifest] = useState<AgentToolManifestItem[]>([]);
  const [activeCategory, setActiveCategory] = useState<Category | null>(null);
  const [expandedServers, setExpandedServers] = useState<Set<string>>(new Set());
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectableManifest = useMemo(
    () => manifest.filter(agent => agent.name !== DEFAULT_AGENT_NAME),
    [manifest]
  );

  const activeAgent = useMemo(
    () => selectableManifest.find(agent => agent.name === agentName) ?? selectableManifest[0],
    [agentName, selectableManifest]
  );
  const selectedTools = useMemo(
    () => activeAgent ? selectedToolsByAgent[activeAgent.name] ?? [] : [],
    [activeAgent, selectedToolsByAgent]
  );

  const loadManifest = useCallback(async () => {
    if (!token) return;

    setIsLoading(true);
    setError(null);
    try {
      const response = await getAgentToolManifest(token);
      setManifest(response.agents);
    } catch (err) {
      console.error('Failed to load agent tool manifest:', err);
      setError(err instanceof Error ? err.message : 'Failed to load tools');
    } finally {
      setIsLoading(false);
    }
  }, [token]);

  useEffect(() => {
    loadManifest();
  }, [loadManifest]);

  useEffect(() => {
    if (selectableManifest.length === 0) return;

    const nextAgent = selectableManifest.find(agent => agent.name === agentName)
      ?? selectableManifest[0];
    if (nextAgent && nextAgent.name !== agentName) {
      onAgentChange(nextAgent.name);
    }
  }, [agentName, onAgentChange, selectableManifest]);

  useEffect(() => {
    onExpandChange?.(activeCategory !== null);
  }, [activeCategory, onExpandChange]);

  useEffect(() => () => onExpandChange?.(false), [onExpandChange]);

  const currentServers = activeAgent && activeCategory
    ? activeAgent.tools[activeCategory]
    : [];

  const counts = useMemo(() => {
    if (!activeAgent) {
      return { tool: [0, 0], mcp: [0, 0], subagent: [0, 0] } as Record<Category, [number, number]>;
    }
    return (Object.keys(CATEGORY_CONFIG) as Category[]).reduce((acc, category) => {
      const tools = activeAgent.tools[category].flatMap(server => server.tools);
      acc[category] = [
        tools.filter(tool => selectedTools.includes(tool.name)).length,
        tools.length,
      ];
      return acc;
    }, {} as Record<Category, [number, number]>);
  }, [activeAgent, selectedTools]);

  const setActiveAgentTools = useCallback((tools: string[]) => {
    if (!activeAgent) return;
    onSelectionChange(activeAgent.name, tools);
  }, [activeAgent, onSelectionChange]);

  const handleToggleTool = useCallback((toolName: string) => {
    if (disabled) return;
    setActiveAgentTools(
      selectedTools.includes(toolName)
        ? selectedTools.filter(name => name !== toolName)
        : [...selectedTools, toolName]
    );
  }, [disabled, selectedTools, setActiveAgentTools]);

  const handleToggleServer = useCallback((server: ServerInfo, select: boolean) => {
    if (disabled) return;
    const serverToolNames = server.tools.map(tool => tool.name);
    if (select) {
      const next = [...selectedTools];
      serverToolNames.forEach(name => {
        if (!next.includes(name)) next.push(name);
      });
      setActiveAgentTools(next);
    } else {
      setActiveAgentTools(
        selectedTools.filter(name => !serverToolNames.includes(name))
      );
    }
  }, [disabled, selectedTools, setActiveAgentTools]);

  const handleToggleExpandServer = useCallback((serverName: string) => {
    setExpandedServers(prev => {
      const next = new Set(prev);
      if (next.has(serverName)) {
        next.delete(serverName);
      } else {
        next.add(serverName);
      }
      return next;
    });
  }, []);

  return (
    <div className="mb-2">
      <div className="flex items-center gap-2 mb-2 overflow-x-auto">
        {isLoading && (
          <Loader2 className="w-4 h-4 animate-spin text-gray-400 flex-shrink-0" />
        )}

        {selectableManifest.length > 0 && (
          <select
            value={activeAgent?.name ?? agentName}
            onChange={(event) => onAgentChange(event.target.value)}
            disabled={disabled || isLoading}
            className="px-2 py-1.5 text-sm rounded-lg border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200"
          >
            {selectableManifest.map(agent => (
              <option key={agent.name} value={agent.name}>
                {agent.display_name}
              </option>
            ))}
          </select>
        )}

        {(Object.keys(CATEGORY_CONFIG) as Category[]).map(category => {
          const config = CATEGORY_CONFIG[category];
          const Icon = config.icon;
          const [selectedCount, totalCount] = counts[category] ?? [0, 0];
          if (totalCount === 0) return null;

          return (
            <button
              key={category}
              type="button"
              onClick={() => {
                setActiveCategory(prev => prev === category ? null : category);
              }}
              disabled={isLoading}
              className={`
                flex items-center gap-2 px-3 py-2 rounded-lg text-sm
                transition-colors duration-150 whitespace-nowrap
                ${activeCategory === category
                  ? config.activeClass
                  : `text-gray-700 dark:text-gray-300 ${config.hoverClass}`
                }
              `}
            >
              <Icon className={`w-4 h-4 ${config.iconClass}`} />
              <span className="font-medium">{config.label}</span>
              <span className="text-xs text-gray-500 dark:text-gray-400">
                ({selectedCount}/{totalCount})
              </span>
              {activeCategory === category ? (
                <ChevronUp className="w-4 h-4" />
              ) : (
                <ChevronDown className="w-4 h-4" />
              )}
            </button>
          );
        })}
      </div>

      {error && (
        <div className="text-sm text-red-500 text-center py-2">{error}</div>
      )}

      {activeCategory && (
        <div className="bg-gray-50/50 dark:bg-gray-800/50 rounded-lg border border-gray-200 dark:border-gray-600 p-3 space-y-2">
          {currentServers.length > 0 ? (
            currentServers.map(server => (
              <ServerCard
                key={`${server.type}:${server.name}`}
                server={server}
                selectedTools={selectedTools}
                onToggleTool={handleToggleTool}
                onToggleAll={handleToggleServer}
                disabled={disabled}
                isExpanded={expandedServers.has(`${server.type}:${server.name}`)}
                onToggleExpand={() => {
                  handleToggleExpandServer(`${server.type}:${server.name}`);
                }}
              />
            ))
          ) : (
            <div className="text-sm text-gray-500 dark:text-gray-400 text-center py-2">
              No tools available
            </div>
          )}
        </div>
      )}
    </div>
  );
}
