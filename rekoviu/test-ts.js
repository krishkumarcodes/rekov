const fs = require('fs');
const ts = require('C:/Users/Roset/Desktop/rekov-6.0.0/rekoviu/node_modules/typescript');
const code = fs.readFileSync('src/app/receptionist/page.tsx', 'utf8');
const sourceFile = ts.createSourceFile('page.tsx', code, ts.ScriptTarget.Latest, true);
function printErrors(node) {
    if (node.parseDiagnostics && node.parseDiagnostics.length > 0) {
        node.parseDiagnostics.forEach(d => {
            const pos = sourceFile.getLineAndCharacterOfPosition(d.start);
            console.log(`Error at line ${pos.line + 1}: ${d.messageText}`);
        });
    }
}
printErrors(sourceFile);
