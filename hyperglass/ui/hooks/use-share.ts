import { useMutation, useQuery } from '@tanstack/react-query';

export class ShareError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = 'ShareError';
    this.status = status;
  }
}

const parseError = async (res: Response): Promise<string> => {
  try {
    return (await res.text()) || res.statusText;
  } catch {
    return res.statusText;
  }
};

export const useShareCreate = () =>
  useMutation<ShareCreateResponse, ShareError, string>({
    mutationFn: async (cacheId: string) => {
      const res = await fetch(`/api/query/share/${cacheId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      if (!res.ok) throw new ShareError(res.status, await parseError(res));
      return res.json() as Promise<ShareCreateResponse>;
    },
  });

export const useShareGet = (shareId: string | undefined) =>
  useQuery<ShareResponse, ShareError>({
    queryKey: ['/api/query/share', shareId],
    enabled: Boolean(shareId),
    queryFn: async () => {
      const res = await fetch(`/api/query/share/${shareId}`);
      if (!res.ok) throw new ShareError(res.status, await parseError(res));
      return res.json() as Promise<ShareResponse>;
    },
  });
