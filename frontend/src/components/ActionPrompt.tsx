import type { NextActionPrompt } from "../hooks/useInspectionRun";

type ActionPromptProps = {
  prompt: NextActionPrompt;
  onPrimary: () => void;
  onDismiss: () => void;
};

export function ActionPrompt({ prompt, onPrimary, onDismiss }: ActionPromptProps) {
  return (
    <div className="action-prompt-backdrop" role="presentation">
      <section className="action-prompt-dialog" role="dialog" aria-modal="true" aria-labelledby="action-prompt-title">
        <div>
          <span>Next window</span>
          <h2 id="action-prompt-title">{prompt.title}</h2>
          <p>{prompt.message}</p>
        </div>
        <div className="action-prompt-actions">
          <button type="button" className="primary-action" onClick={onPrimary}>
            {prompt.primaryLabel}
          </button>
          <button type="button" onClick={onDismiss}>
            Stay Here
          </button>
        </div>
      </section>
    </div>
  );
}
