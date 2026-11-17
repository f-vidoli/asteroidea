import type { JsonObject, JsonValue, MemoryTier, ScreenTarget, WidgetSlot } from '../types';

export const NODE_TYPES = {
  BOX_LAYOUT: 'BoxLayout',
  SCROLL_VIEW: 'ScrollView',
  LABEL: 'Label',
  BUTTON: 'Button',
  SPACER: 'Spacer',
} as const;

export type NodeType = (typeof NODE_TYPES)[keyof typeof NODE_TYPES];

export const ACTION_VERBS = {
  STORAGE_SET: 'storage.set',
  EMIT: 'emit',
  REFRESH: 'refresh',
} as const;

export type ActionVerb = (typeof ACTION_VERBS)[keyof typeof ACTION_VERBS];

export type LayoutPropValue = string | number | boolean;

export interface LayoutAction {
  action: ActionVerb;
  tier?: MemoryTier;
  key?: string;
  value?: JsonValue | string;
  event?: string;
  data?: JsonObject;
}

export interface LayoutNode {
  type: NodeType;
  id?: string;
  props?: Record<string, LayoutPropValue>;
  children?: LayoutNode[];
  on_press?: LayoutAction[];
}

export interface LayoutDocument {
  name: string;
  surface?: ScreenTarget;
  slot?: WidgetSlot;
  root: LayoutNode;
}

export const LAYOUT_PROPS = [
  'text',
  'color',
  'background',
  'padding',
  'spacing',
  'orientation',
  'font_size',
  'class',
  'width',
  'height',
  'min_height',
] as const;

export type LayoutProp = (typeof LAYOUT_PROPS)[number];
