const puppeteer = require('puppeteer');
const path = require('path');

(async () => {
  const browser = await puppeteer.launch();
  const page = await browser.newPage();
  
  const htmlPath = path.resolve(__dirname, '../output/The_Jeff_on_10th_Report_Styled.html');
  const pdfPath = path.resolve(__dirname, '../output/The_Jeff_on_10th_Report_Styled.pdf');
  
  await page.goto(`file://${htmlPath}`, {waitUntil: 'networkidle0'});
  
  await page.pdf({
    path: pdfPath,
    format: 'Letter',
    printBackground: true,
    margin: {
      top: '0px',
      right: '0px',
      bottom: '0px',
      left: '0px'
    }
  });

  await browser.close();
  console.log(`Stylish PDF created successfully at: ${pdfPath}`);
})();
