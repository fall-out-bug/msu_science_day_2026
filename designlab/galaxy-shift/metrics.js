/* Metrics use the predictions displayed on the selected split. */
(function(root) {
  'use strict';
  function calculate(predictions, classes) {
    if (!Array.isArray(predictions) || !Array.isArray(classes) || !classes.length || new Set(classes).size !== classes.length) throw new Error('Некорректные данные для расчёта метрик.');
    const matrix = classes.map(() => classes.map(() => 0));
    for (const item of predictions) {
      const actual = classes.indexOf(item.expected), predicted = classes.indexOf(item.predicted);
      if (actual < 0 || predicted < 0) throw new Error('Неизвестный класс в предсказании.');
      matrix[actual][predicted]++;
    }
    const ratio = (a,b) => b ? a / b : null;
    const perClass = classes.map((id, i) => {
      const tp = matrix[i][i], fp = matrix.reduce((sum,row) => sum + row[i], 0) - tp;
      const fn = matrix[i].reduce((sum,value) => sum + value, 0) - tp;
      return {id,tp,fp,fn,precision:ratio(tp,tp+fp),recall:ratio(tp,tp+fn),f1:ratio(2*tp,2*tp+fp+fn)};
    });
    return {matrix,perClass,accuracy:ratio(perClass.reduce((sum,row) => sum+row.tp,0),predictions.length),macroF1:predictions.length ? perClass.reduce((sum,row) => sum+(row.f1 ?? 0),0)/classes.length : null};
  }
  root.GalaxyMetrics = Object.freeze({calculate});
})(globalThis);
