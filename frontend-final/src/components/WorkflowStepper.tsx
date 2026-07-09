const STEPS = ["Inspection details", "Categories", "Upload evidence", "Review and start"];

type WorkflowStepperProps = {
  activeIndex: number;
};

export function WorkflowStepper({ activeIndex }: WorkflowStepperProps) {
  return (
    <ol className="workflow-stepper" aria-label="Inspection setup steps">
      {STEPS.map((step, index) => (
        <li key={step} className={index <= activeIndex ? "step step-active" : "step"}>
          <span>{index + 1}</span>
          <p>{step}</p>
        </li>
      ))}
    </ol>
  );
}
