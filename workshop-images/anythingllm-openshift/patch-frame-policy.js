const fs = require("fs");

const target = process.argv[2];
if (!target) {
  throw new Error("usage: node patch-frame-policy.js <server-index.js>");
}

const source = fs.readFileSync(target, "utf8");
const needle = 'res.setHeader("X-Frame-Options", "DENY");';
const occurrences = source.split(needle).length - 1;
if (occurrences !== 1) {
  throw new Error(
    `expected one AnythingLLM frame-deny header, found ${occurrences}`
  );
}

const anchor = 'const FILE_LIMIT = "3GB";\n';
if (!source.includes(anchor)) {
  throw new Error("AnythingLLM middleware anchor was not found");
}

const middleware = `${anchor}
const launchpadFrameAncestor = process.env.LAUNCHPAD_FRAME_ANCESTOR;
const launchpadFrameAncestorIsValid =
  !!launchpadFrameAncestor &&
  /^https:\\/\\/[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?(?::[0-9]+)?$/i.test(
    launchpadFrameAncestor
  );

app.use((_, response, next) => {
  if (launchpadFrameAncestorIsValid) {
    response.setHeader(
      "Content-Security-Policy",
      \`frame-ancestors 'self' \${launchpadFrameAncestor}\`
    );
  } else {
    response.setHeader("X-Frame-Options", "DENY");
  }
  next();
});
`;

const staticHeader = `if (launchpadFrameAncestorIsValid) {
          res.removeHeader("X-Frame-Options");
        } else {
          res.setHeader("X-Frame-Options", "DENY");
        }`;

fs.writeFileSync(
  target,
  source.replace(anchor, middleware).replace(needle, staticHeader)
);
