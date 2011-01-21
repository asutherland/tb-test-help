
wy.localizeWidgets([{
  name: "zing-overview",
  structure: {
    row: {
      // bork 7 borks
      count: ["bork ", {bind: "count"}, " borks"],
      
      count: {
        plural0: [],
        plural1: [],
        pluralN: [],
        
      },
      
      count: [{bind: "count", format: "#,####"},
              " borks",
              {bind: "count"}],
      ridiculous: [0, " bork", 2],
      
      what: ["brok ", null],
      
      what: {bind: "kind", formatter: FUNCTION},
    },
  },
}]);
