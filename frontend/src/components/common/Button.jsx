/** 공통 버튼. variant/size는 styles/index.css의 .btn-* 클래스와 1:1로 맞춘다. */
function Button({
  variant = "default", // default | primary | danger
  size = "md", // md | sm
  block = false,
  type = "button",
  className = "",
  children,
  ...rest
}) {
  const classes = [
    "btn",
    variant !== "default" ? `btn-${variant}` : "",
    size === "sm" ? "btn-sm" : "",
    block ? "btn-block" : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <button type={type} className={classes} {...rest}>
      {children}
    </button>
  );
}

export default Button;
