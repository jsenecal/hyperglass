export declare global {
  type Dict<T = string> = Record<string, T>;

  type ValueOf<T> = T[keyof T];

  type Nullable<T> = T | null;

  type Get<T, K extends keyof T> = T[K];

  type Swap<T, K extends keyof T, V> = Record<K, V> & Omit<T, K>;

  type ArrayElement<ArrayType extends readonly unknown[]> =
    ArrayType extends readonly (infer ElementType)[] ? ElementType : never;

  type RPKIState = 0 | 1 | 2 | 3;

  type ResponseLevel = 'success' | 'warning' | 'error' | 'danger';

  type Route = {
    prefix: string;
    active: boolean;
    age: number;
    weight: number;
    med: number;
    local_preference: number;
    as_path: number[];
    communities: string[];
    next_hop: string;
    source_as: number;
    source_rid: string;
    peer_rid: string;
    rpki_state: RPKIState;
  };

  type RouteField = { [K in keyof Route]: Route[K] };

  type StructuredResponse = {
    vrf: string;
    count: number;
    routes: Route[];
    winning_weight: 'high' | 'low';
  };

  type QueryResponse = {
    id: string;
    random: string;
    cached: boolean;
    runtime: number;
    level: ResponseLevel;
    timestamp: string;
    keywords: string[];
    output: string | StructuredResponse;
    format: 'text/plain' | 'application/json';
  };

  interface ResultSnapshot {
    id: string;
    output: QueryResponse['output'];
    format: QueryResponse['format'];
    // Backend stores 'success' for cached/shared results; typed as ResponseLevel for future warning/error support.
    level: ResponseLevel;
    timestamp: string;
    runtime: number;
    cached: boolean;
    keywords: string[];
    // Nested dict keys are NOT camelCased by backend pydantic; keep snake_case.
    queryLabels: { location: string; type: string };
  }

  interface ShareResponse extends ResultSnapshot {
    shared: boolean;
    // Nested dict keys are NOT camelCased by backend pydantic; keep snake_case.
    query: { query_location: string; query_target: string | string[]; query_type: string };
    createdAt: string;
    expiresAt: string;
  }

  type ShareCreateResponse = {
    id: string;
    url: string;
    expiresAt: string;
  };

  type RequiredProps<T> = { [P in keyof T]-?: Exclude<T[P], undefined> };

  declare namespace NodeJS {
    export interface ProcessEnv {
      hyperglass: { favicons: import('./config').Favicon[]; version: string };
      buildId: string;
      UI_PARAMS: import('./config').Config;
    }
  }
}

declare module 'hyperglass.json' {
  type Config = import('./config').Config;
  export default Config;
}

declare module 'react' {
  // Enable generic typing with forwardRef.
  // eslint-disable-next-line @typescript-eslint/ban-types
  function forwardRef<T, P = {}>(
    render: (props: P, ref: React.Ref<T>) => React.ReactElement | null,
  ): (props: P & React.RefAttributes<T>) => React.ReactElement | null;
}
